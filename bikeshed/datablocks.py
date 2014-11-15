# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import re
import json
import copy

import config
import biblio
from .messages import *

# This function does a single pass through the doc,
# finding all the "data blocks" and processing them.
# A "data block" is any <pre> or <xmp> element.
#
# When a data block is found, the *contents* of the block
# are passed to the appropriate processing function as an
# array of lines.  The function should return a new array
# of lines to replace the *entire* block.
#
# That is, we give you the insides, but replace the whole
# thing.
#
# Additionally, we pass in the tag-name used (pre or xmp)
# and the line with the content, in case it has useful data in it.
def transformDataBlocks(doc):
    inBlock = False
    blockTypes = {
        'propdef': transformPropdef,
        'descdef': transformDescdef,
        'elementdef': transformElementdef,
        'railroad': transformRailroad,
        'biblio': transformBiblio,
        'anchors': transformAnchors,
        'pre': transformPre
    }
    blockType = ""
    tagName = ""
    startLine = 0
    replacements = []
    for (i, line) in enumerate(doc.lines):
        # Look for the start of a block.
        match = re.match(r"\s*<(pre|xmp)(.*)", line, re.I)
        if match and not inBlock:
            inBlock = True
            startLine = i
            tagName = match.group(1)
            typeMatch = re.search("|".join(blockTypes.keys()), match.group(2))
            if typeMatch:
                blockType = typeMatch.group(0)
            else:
                blockType = "pre"
        # Look for the end of a block.
        match = re.match(r"(.*)</"+tagName+">(.*)", line, re.I)
        if match and inBlock:
            inBlock = False
            if startLine == i:
                # Single-line <pre>.
                match = re.match(r"\s*(<{0}[^>]*>)(.+)</{0}>(.*)".format(tagName), line, re.I)
                doc.lines[i] = match.group(3)
                replacements.append({
                    'start': i,
                    'end': i,
                    'value': blockTypes[blockType](
                        lines=[match.group(2)],
                        tagName=tagName,
                        firstLine=match.group(1),
                        doc=doc)})
            elif re.match(r"^\s*$", match.group(1)):
                # End tag was the first tag on the line.
                # Remove the tag from the line.
                doc.lines[i] = match.group(2)
                replacements.append({
                    'start': startLine,
                    'end': i,
                    'value': blockTypes[blockType](
                        lines=doc.lines[startLine+1:i],
                        tagName=tagName,
                        firstLine=doc.lines[startLine],
                        doc=doc)})
            else:
                # End tag was at the end of line of useful content.
                # Trim this line to be only the block content.
                doc.lines[i] = match.group(1)
                # Put the after-tag content on the next line.
                doc.lines.insert(i+1, match.group(2))
                replacements.append({
                    'start': startLine,
                    'end': i+1,
                    'value': blockTypes[blockType](
                        lines=doc.lines[startLine+1:i+1],
                        tagName=tagName,
                        firstLine=doc.lines[startLine],
                        doc=doc)})
            tagName = ""
            blockType = ""

    # Make the replacements, starting from the bottom up so I
    # don't have to worry about offsets becoming invalid.
    for rep in reversed(replacements):
        doc.lines[rep['start']:rep['end']] = rep['value']


def transformPre(lines, tagName, firstLine, **kwargs):
    # If the last line in the source is a </code></pre>,
    # the generic processor will turn that into a final </code> line,
    # which'll mess up the indent finding.
    # Instead, specially handle this case.
    if len(lines) == 0:
        return [firstLine, "</{0}>".format(tagName)]

    if re.match(r"\s*</code>\s*$", lines[-1]):
        lastLine = "</code></{0}>".format(tagName)
        lines = lines[:-1]
    else:
        lastLine = "</{0}>".format(tagName)

    if len(lines) == 0:
        return [firstLine, lastLine]

    indent = float("inf")
    for (i, line) in enumerate(lines):
        if line.strip() == "":
            continue

        # Use tabs in the source, but spaces in the output,
        # because tabs are ginormous in HTML.
        lines[i] = lines[i].replace("\t", "  ")

        # Find the line with the shortest whitespace prefix.
        # (It might not be the first!)
        indent = min(indent, len(re.match(r" *", lines[i]).group(0)))

    if indent == float("inf"):
        indent = 0

    # Strip off the whitespace prefix from each line
    for (i, line) in enumerate(lines):
        if line.strip() == "":
            continue
        lines[i] = lines[i][indent:]
    # Put the first/last lines back into the results.
    lines[0] = firstLine.rstrip() + lines[0]
    lines.append(lastLine)
    return lines


def transformPropdef(lines, doc, firstLine, **kwargs):
    attrs = OrderedDict()
    parsedAttrs = parseDefBlock(lines, "propdef")
    # Displays entries in the order specified in attrs,
    # then if there are any unknown parsedAttrs values,
    # they're displayed afterward in the order they were specified.
    # attrs with a value of None are required to be present in parsedAttrs;
    # attrs with any other value are optional, and use the specified value if not present in parsedAttrs
    if "partial" in firstLine or "New values" in parsedAttrs:
        attrs["Name"] = None
        attrs["New values"] = None
        ret = ["<table class='definition propdef partial'>"]
    elif "shorthand" in firstLine:
        attrs["Name"] = None
        attrs["Value"] = None
        for defaultKey in ["Initial", "Applies to", "Inherited", "Percentages", "Media", "Computed value", "Animatable"]:
            attrs[defaultKey] = "see individual properties"
        ret = ["<table class='definition propdef'>"]
    else:
        attrs["Name"] = None
        attrs["Value"] = None
        attrs["Initial"] = None
        attrs["Applies to"] = "all elements"
        attrs["Inherited"] = None
        attrs["Percentages"] = "n/a"
        attrs["Media"] = "visual"
        attrs["Computed value"] = "as specified"
        attrs["Animatable"] = "no"
        ret = ["<table class='definition propdef'>"]
    for key, val in attrs.items():
        if key in parsedAttrs or val is not None:
            if key in parsedAttrs:
                val = parsedAttrs[key]
            if key in ("Value", "New values"):
                ret.append("<tr><th>{0}:<td class='prod'>{1}".format(key, val))
            else:
                ret.append("<tr><th>{0}:<td>{1}".format(key, val))
        else:
            die("The propdef for '{0}' is missing a '{1}' line.", parsedAttrs.get("Name", "???"), key)
            continue
    for key, val in parsedAttrs.items():
        if key in attrs:
            continue
        ret.append("<tr><th>{0}:<td>{1}".format(key, val))
    ret.append("</table>")
    return ret

# TODO: Make these functions match transformPropdef's new structure
def transformDescdef(lines, doc, firstLine, **kwargs):
    vals = parseDefBlock(lines, "descdef")
    if "partial" in firstLine or "New values" in vals:
        requiredKeys = ["Name", "For"]
        ret = ["<table class='definition descdef partial' data-dfn-for='{0}'>".format(vals.get("For", ""))]
    if "mq" in firstLine:
        requiredKeys = ["Name", "For", "Value"]
        ret = ["<table class='definition descdef mq' data-dfn-for='{0}'>".format(vals.get("For",""))]
    else:
        requiredKeys = ["Name", "For", "Value", "Initial"]
        ret = ["<table class='definition descdef' data-dfn-for='{0}'>".format(vals.get("For", ""))]
    for key in requiredKeys:
        if key == "For":
            ret.append("<tr><th>{0}:<td><a at-rule>{1}</a>".format(key, vals.get(key,'')))
        elif key == "Value":
            ret.append("<tr><th>{0}:<td class='prod'>{1}".format(key, vals.get(key,'')))
        elif key in vals:
            ret.append("<tr><th>{0}:<td>{1}".format(key, vals.get(key,'')))
        else:
            die("The descdef for '{0}' is missing a '{1}' line.", vals.get("Name", "???"), key)
            continue
    for key in vals.viewkeys() - requiredKeys:
        ret.append("<tr><th>{0}:<td>{1}".format(key, vals[key]))
    ret.append("</table>")
    return ret

def transformElementdef(lines, doc, **kwargs):
    attrs = OrderedDict()
    parsedAttrs = parseDefBlock(lines, "elementdef")
    if "Attribute groups" in parsedAttrs or "Attributes" in parsedAttrs:
        html = "<ul>"
        if "Attribute groups" in parsedAttrs:
            groups = [x.strip() for x in parsedAttrs["Attribute groups"].split(",")]
            for group in groups:
                html += "<li><a dfn data-element-attr-group>{0}</a>".format(group)
            del parsedAttrs["Attribute groups"]
        if "Attributes" in parsedAttrs:
            atts = [x.strip() for x in parsedAttrs["Attributes"].split(",")]
            for att in atts:
                html += "<li><a element-attr>{0}</a>".format(att)
        html += "</ul>"
        parsedAttrs["Attributes"] = html


    # Displays entries in the order specified in attrs,
    # then if there are any unknown parsedAttrs values,
    # they're displayed afterward in the order they were specified.
    # attrs with a value of None are required to be present in parsedAttrs;
    # attrs with any other value are optional, and use the specified value if not present in parsedAttrs
    attrs["Name"] = None
    attrs["Categories"] = None
    attrs["Contexts"] = None
    attrs["Content model"] = None
    attrs["Attributes"] = None
    attrs["Dom interfaces"] = None
    ret = ["<table class='definition-table elementdef'>"]
    for key, val in attrs.items():
        if key in parsedAttrs or val is not None:
            if key in parsedAttrs:
                val = parsedAttrs[key]
            if key == "Name":
                ret.append("<tr><th>Name:<td>")
                ret.append(', '.join("<dfn element>{0}</dfn>".format(x.strip()) for x in val.split(",")))
            elif key == "Content model":
                ret.append("<tr><th>{0}:<td>".format(key))
                ret.extend(val.split("\n"))
            elif key == "Categories":
                ret.append("<tr><th>Categories:<td>")
                ret.append(', '.join("<a dfn>{0}</a>".format(x.strip()) for x in val.split(",")))
            elif key == "Dom interfaces":
                ret.append("<tr><th>DOM Interfaces:<td>")
                ret.append(', '.join("<a interface>{0}</a>".format(x.strip()) for x in val.split(",")))
            else:
                ret.append("<tr><th>{0}:<td>{1}".format(key, val))
        else:
            die("The elementdef for '{0}' is missing a '{1}' line.", parsedAttrs.get("Name", "???"), key)
            continue
    for key, val in parsedAttrs.items():
        if key in attrs:
            continue
        ret.append("<tr><th>{0}:<td>{1}".format(key, val))
    ret.append("</table>")
    return ret



def parseDefBlock(lines, type):
    vals = OrderedDict()
    lastKey = None
    for line in lines:
        match = re.match(r"\s*([^:]+):\s*(\S.*)", line)
        if match is None:
            if lastKey is not None and (line.strip() == "" or re.match(r"\s+", line)):
                key = lastKey
                val = line.strip()
            else:
                die("Incorrectly formatted {2} line for '{0}':\n{1}", vals.get("Name", "???"), line, type)
                continue
        else:

            key = match.group(1).strip().capitalize()
            lastKey = key
            val = match.group(2).strip()
        if key in vals:
            vals[key] += "\n"+val
        else:
            vals[key] = val
    return vals

def transformRailroad(lines, doc, **kwargs):
    import StringIO
    import railroadparser
    ret = [
        "<div class='railroad'>",
        "<style>svg.railroad-diagram{background-color:hsl(30,20%,95%);}svg.railroad-diagram path{stroke-width:3;stroke:black;fill:rgba(0,0,0,0);}svg.railroad-diagram text{font:bold 14px monospace;text-anchor:middle;}svg.railroad-diagram text.label{text-anchor:start;}svg.railroad-diagram text.comment{font:italic 12px monospace;}svg.railroad-diagram rect{stroke-width:3;stroke:black;fill:hsl(120,100%,90%);}</style>"]
    code = ''.join(lines)
    diagram = railroadparser.parse(code)
    temp = StringIO.StringIO()
    diagram.writeSvg(temp.write)
    ret.append(temp.getvalue())
    temp.close()
    ret.append("</div>")
    return ret

def transformBiblio(lines, doc, **kwargs):
    biblio.processSpecrefBiblioFile(''.join(lines), doc.refs.biblios, order=1)
    return []

def transformAnchors(lines, doc, **kwargs):
    try:
        anchors = json.loads(''.join(lines))
    except Exception, e:
        die("JSON parse error:\n{0}", e)
        return []

    def checkTypes(anchor, key, field, *types):
        if field not in anchor:
            return True
        val = anchor[field]
        for fieldType in types:
            if isinstance(val, fieldType):
                break
        else:
            die("Field '{1}' of inline anchor for '{0}' must be a {3}. Got a '{2}'.", key, field, type(val), ' or '.join(str(t) for t in types))
            return False
        return True

    for anchor in anchors:
        # Check all the mandatory fields
        for field in ["linkingText", "type", "shortname", "level", "url"]:
            if field not in anchor:
                die("Inline anchor for '{0}' is missing the '{1}' field.", key, field)
                continue
        if "for" not in anchor:
            anchor["for"] = []
        key = anchor['linkingText'] if isinstance(anchor['linkingText'], basestring) else list(anchor['linkingText'])[0]
        # String fields
        for field in ["type", "shortname", "url"]:
            if not checkTypes(anchor, key, field, basestring):
                continue
            anchor[field] = anchor[field].strip()+"\n"
        if "status" in anchor:
            if anchor['status'].strip() not in ["current", "dated", "local"]:
                die("Field 'status' of inline anchor for '{0}' must be 'current', 'dated', or 'local'. Got '{1}'.", key, anchor['status'].strip())
                continue
            else:
                # TODO Convert the internal representation from ED/TR to current/dated
                anchor['status'] = "ED\n" if anchor['status'] == "current\n" else "TR\n"
        else:
            anchor['status'] = "local"
        # String or int fields, convert to string
        for field in ["level"]:
            if not checkTypes(anchor, key, field, basestring, int):
                continue
            anchor[field] = unicode(anchor[field]).strip() + "\n"
        anchor['spec'] = "{0}-{1}\n".format(anchor['shortname'].strip(), anchor['level'].strip())
        anchor['export'] = True
        # String or list-of-strings fields, convert to list
        for field in ["linkingText", "for"]:
            if field not in anchor:
                continue
            if not checkTypes(anchor, key, field, basestring, list, dict):
                continue
            if isinstance(anchor[field], basestring):
                anchor[field] = [anchor[field]]
            if isinstance(anchor[field], list):
                for i,line in enumerate(anchor[field]):
                    if not isinstance(line, basestring):
                        die("All of the values for field '{1}' of inline anchor for '{0}' must be strings. Got a '{2}'.", key, field, type(line))
                        continue
                    anchor[field][i] = re.sub(r'\s+', ' ', anchor[field][i].strip()) + "\n"
            elif isinstance(anchor[field], dict):
                for text,val in anchor[field].items():
                    if not isinstance(val, basestring):
                        die("All of the values for field '{1}' of inline anchor for '{0}' must be strings. Got a '{2}'.", key, field, type(line))
                        continue
                    fixedText = re.sub(r'\s+', ' ', text.strip()) + "\n"
                    anchor[field][fixedText] = anchor[field][text]
                    del anchor[field][text]


        if anchor.get("anchor macro"):
            # The anchor is actually a macro, defining a template for generating URLs for the real anchors.
            texts = anchor['linkingText']
            if isinstance(texts, dict):
                # {term:suffix}
                for text,suffix in texts.items():
                    clone = copy.deepcopy(anchor)
                    clone['url'] = anchor['url'] + suffix
                    doc.refs.refs[text.lower()].append(clone)
            elif isinstance(texts, list):
                # [term]
                for text in texts:
                    clone = copy.deepcopy(anchor)
                    clone['url'] = anchor['url'] + config.simplifyText(text)
                    doc.refs.refs[text.lower()].append(clone)
            # Now stash the anchor macro away, so any <a spec> anchors pointing to this spec
            # can also still autogenerate, despite not being listed here.
            doc.refs.anchorMacros[anchor['spec']] = anchor
            doc.refs.anchorMacros[anchor['shortname']] = anchor
        else:
            for text in anchor['linkingText']:
                doc.refs.refs[text.lower()].append(anchor)

    return []