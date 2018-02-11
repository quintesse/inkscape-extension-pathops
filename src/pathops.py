#!/usr/bin/env python
"""
pathops.py - Inkscape extension to apply multiple path operations

This extension takes a selection of path and a group of paths, or several
paths, and applies a path operation with the top-most path in the z-order, and
each selected path or each child of a selected group underneath.

Copyright (C) 2014  Ryan Lerch (multiple difference)
              2016  Maren Hachmann <marenhachmannATyahoo.com>
                    (refactoring, extend to multibool)
              2017  su_v <suv-sf@users.sf.net>
                    Rewrite to support large selections (process in chunks), to
                    improve performance (support groups, z-sort ids with python
                    instead of external query), and to extend GUI options.

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License along
with this program; if not, write to the Free Software Foundation, Inc.,
51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
"""
# pylint: disable=too-many-ancestors

# standard library
import os
from subprocess import Popen, PIPE
import time

# local library
try:
    import inkex_local as inkex
except ImportError:
    import inkex
import simplestyle


__version__ = '0.4'


# Global "constants"
SVG_SHAPES = ('rect', 'circle', 'ellipse', 'line', 'polyline', 'polygon')


# ----- general helper functions

def timed(f):
    """Minimalistic timer for functions."""
    # pylint: disable=invalid-name
    start = time.time()
    ret = f()
    elapsed = time.time() - start
    return ret, elapsed


# ----- SVG element helper functions

def get_defs(node):
    """Find <defs> in children of *node*, return first one found."""
    path = '/svg:svg//svg:defs'
    try:
        return node.xpath(path, namespaces=inkex.NSS)[0]
    except IndexError:
        return inkex.etree.SubElement(node, inkex.addNS('defs', 'svg'))


def is_group(node):
    """Check node for group tag."""
    return node.tag == inkex.addNS('g', 'svg')


def is_path(node):
    """Check node for path tag."""
    return node.tag == inkex.addNS('path', 'svg')


def is_basic_shape(node):
    """Check node for SVG basic shape tag."""
    return node.tag in (inkex.addNS(tag, 'svg') for tag in SVG_SHAPES)


def is_custom_shape(node):
    """Check node for Inkscape custom shape type."""
    return inkex.addNS('type', 'sodipodi') in node.attrib


def is_shape(node):
    """Check node for SVG basic shape tag or Inkscape custom shape type."""
    return is_basic_shape(node) or is_custom_shape(node)


def has_path_effect(node):
    """Check node for Inkscape path-effect attribute."""
    return inkex.addNS('path-effect', 'inkscape') in node.attrib


def is_modifiable_path(node):
    """Check node for editable path data."""
    return is_path(node) and not (has_path_effect(node) or
                                  is_custom_shape(node))


def is_image(node):
    """Check node for image tag."""
    return node.tag == inkex.addNS('image', 'svg')


def is_text(node):
    """Check node for text tag."""
    return node.tag == inkex.addNS('text', 'svg')


def does_pathops(node):
    """Check whether node is supported by Inkscape path operations."""
    return (is_path(node) or
            is_shape(node) or
            is_text(node))


# ----- list processing helper functions

def z_sort(node, alist):
    """Return new list sorted in document order (depth-first traversal)."""
    ordered = []
    id_list = list(alist)
    count = len(id_list)
    for element in node.iter():
        element_id = element.get('id')
        if element_id is not None and element_id in id_list:
            id_list.remove(element_id)
            ordered.append(element_id)
            count -= 1
            if not count:
                break
    return ordered


def z_iter(node, alist):
    """Return iterator over ids in document order (depth-first traversal)."""
    id_list = list(alist)
    for element in node.iter():
        element_id = element.get('id')
        if element_id is not None and element_id in id_list:
            id_list.remove(element_id)
            yield element_id


def chunks(alist, max_len):
    """Chunk a list into sublists of max_len length."""
    for i in range(0, len(alist), max_len):
        yield alist[i:i+max_len]


# ----- process external command, files

def run(cmd_format, stdin_str=None, verbose=False):
    """Run command"""
    if verbose:
        inkex.debug(cmd_format)
    out = err = None
    myproc = Popen(cmd_format, shell=False,
                   stdin=PIPE, stdout=PIPE, stderr=PIPE)
    out, err = myproc.communicate(stdin_str)
    if myproc.returncode == 0:
        return out
    elif err is not None:
        inkex.errormsg(err)


def run_pathops(svgfile, top_path, id_list, ink_verb, dry_run=False):
    """Run path ops with top_path on a list of other object ids."""
    # build list with command line arguments
    cmdlist = []
    cmdlist.append("inkscape")
    for node_id in id_list:
        cmdlist.append("--select=" + top_path)
        cmdlist.append("--verb=EditDuplicate")
        cmdlist.append("--select=" + node_id)
        cmdlist.append("--verb=" + ink_verb)
        cmdlist.append("--verb=EditDeselect")
    cmdlist.append("--verb=FileSave")
    cmdlist.append("--verb=FileQuit")
    cmdlist.append("-f")
    cmdlist.append(svgfile)
    # process command list
    if dry_run:
        inkex.debug(cmdlist)
    else:
        run(cmdlist)


def cleanup(tempfile):
    """Clean up tempfile."""
    try:
        os.remove(tempfile)
    except Exception:  # pylint: disable=broad-except
        pass


# ----- PathOps() class, methods

class PathOps(inkex.Effect):
    """Effect-based class to apply Inkscape path operations."""

    def __init__(self):
        """Init base class."""
        inkex.Effect.__init__(self)

        # options
        self.OptionParser.add_option("--ink_verb",
                                     action="store", type="string",
                                     dest="ink_verb", default="SelectionDiff",
                                     help="Inkscape verb for path op")
        self.OptionParser.add_option("--max_ops",
                                     action="store", type="int",
                                     dest="max_ops", default=500,
                                     help="Max ops per external run")
        self.OptionParser.add_option("--recursive_sel",
                                     action="store", type="inkbool",
                                     dest="recursive_sel", default=True,
                                     help="Recurse beyond one group level")
        self.OptionParser.add_option("--keep_top",
                                     action="store", type="inkbool",
                                     dest="keep_top", default=True,
                                     help="Keep top element when done")
        self.OptionParser.add_option("--default_stroke",
                                     action="store", type="string",
                                     dest="default_stroke", default="#000000",
                                     help="Default stroke color")
        self.OptionParser.add_option("--default_stroke_width",
                                     action="store", type="string",
                                     dest="default_stroke_width",
                                     default="1px",
                                     help="Default stroke width")
        self.OptionParser.add_option("--dry_run",
                                     action="store", type="inkbool",
                                     dest="dry_run", default=False,
                                     help="Dry-run without exec")

    def update_attrib(self, node, prop, val):
        """Update checked property."""
        if not self.options.dry_run:
            node.attrib[prop] = val

    def check_props(self, node):
        """Check properties and modify as needed based on options."""
        if self.options.ink_verb == 'SelectionCutPath':
            sdict = simplestyle.parseStyle(node.get('style'))
            fill_color = sdict.get('fill', '')
            if fill_color == 'none' or fill_color.startswith('url('):
                fill_color = None
            stroke_color = fill_color or self.options.default_stroke
            stroke_width = self.unittouu(self.options.default_stroke_width)
            prop = 'stroke'
            if prop not in sdict or sdict[prop] == 'none':
                sdict[prop] = stroke_color
            if prop in node.attrib and node.attrib[prop] == 'none':
                self.update_attrib(node, prop, stroke_color)
            prop = 'stroke-width'
            if prop not in sdict:
                sdict[prop] = stroke_width
            self.update_attrib(node, 'style', simplestyle.formatStyle(sdict))

    def recurse_selection(self, node, id_list, level=0, current=0):
        """Recursively process selection, add checked elements to id list."""
        current += 1
        if not level or current <= level:
            if is_group(node):
                for child in node:
                    id_list = self.recurse_selection(
                        child, id_list, level, current)
        if does_pathops(node):
            self.check_props(node)
            id_list.append(node.get('id'))
        return id_list

    def get_selected_ids(self):
        """Return a list of valid ids for inkscape path operations."""
        id_list = []
        if not len(self.selected):
            pass
        else:
            # level = 0: unlimited recursion into groups
            # level = 1: process top-level groups only
            level = 0 if self.options.recursive_sel else 1
            for node in self.selected.values():
                self.recurse_selection(node, id_list, level)
        if len(id_list) < 2:
            inkex.errormsg("This extension requires at least 2 elements "
                           "of type path, shape or text. "
                           "The elements can be part of selected groups, "
                           "or directly selected.")
            return None
        else:
            return id_list

    def get_sorted_ids(self):
        """Return id of top-most object, and a list with z-sorted ids."""
        top_path = None
        sorted_ids = None
        id_list = self.get_selected_ids()
        if id_list is not None:
            sorted_ids = list(z_iter(self.document.getroot(), id_list))
            top_path = sorted_ids.pop()
        return (top_path, sorted_ids)

    def loop_pathops(self, top_path, other_paths):
        """Loop through selected items and run external command(s)."""
        # init variables
        count = 0
        max_ops = self.options.max_ops or 500
        ink_verb = self.options.ink_verb or "SelectionDiff"
        dry_run = self.options.dry_run
        tempfile = os.path.splitext(self.svg_file)[0] + "-pathops.svg"
        # prepare
        if dry_run:
            inkex.debug("# Top object id: {}".format(top_path))
            inkex.debug("# Other objects total: {}".format(len(other_paths)))
        else:
            with open(tempfile, 'wb') as copycat:
                self.document.write(copycat)
        # loop through sorted id list, process in chunks
        for chunk in chunks(other_paths, max_ops):
            count += 1
            if dry_run:
                inkex.debug("\n# Processing {}. chunk ".format(count) +
                            "with {} objects ...".format(len(chunk)))
            run_pathops(tempfile, top_path, chunk, ink_verb, dry_run)
        # finish up
        if dry_run:
            inkex.debug("\n# {} chunks processed, ".format(count) +
                        "with {} total objects.".format(len(other_paths)))
        else:
            # replace current document with content of temp copy
            xmlparser = inkex.etree.XMLParser(huge_tree=True)
            self.document = inkex.etree.parse(tempfile, parser=xmlparser)
            # optionally delete top-most element when done
            if not self.options.keep_top:
                top_node = self.getElementById(top_path)
                if top_node is not None:
                    top_node.getparent().remove(top_node)
            # purge missing tagrefs (see below)
            self.update_tagrefs()
            # clean up
            cleanup(tempfile)

    def effect(self):
        """Main entry point to process current document."""
        if self.has_tagrefs():
            # unsafe to use with extensions ...
            inkex.errormsg("This document uses Inkscape selection sets. "
                           "Modifying the content with a PathOps extension "
                           "may cause Inkscape to crash on reload or close. "
                           "Please delete the selection sets, "
                           "save the document under a new name and "
                           "try again in a new Inkscape session.")
        else:
            # process selection
            top_path, other_paths = self.get_sorted_ids()
            if top_path is None or other_paths is None:
                return
            else:
                self.loop_pathops(top_path, other_paths)

    # ----- workaround to avoid crash on quit

    # If selection set tagrefs have been deleted as a result of the
    # extension's modifications of the drawing content, inkscape will
    # crash when closing the document window later on unless the tagrefs
    # are checked and cleaned up manually by the extension script.

    # NOTE: crash on reload in the main process (after the extension has
    # finished) still happens if Selection Sets dialog was actually
    # opened and used in the current session ... the extension could
    # create fake (invisible) objects which reuse the ids?
    # No, fake placeholder elements do not prevent the crash on reload
    # if the dialog was opened before.

    # TODO: these checks (and the purging of obsolete tagrefs) probably
    # should be applied in Effect() itself, instead of relying on
    # workarounds in derived classes that modify drawing content.

    @staticmethod
    def get_tagrefs(node):
        """Find tagrefs in node, return list."""
        inkscape_tagrefs = []
        try:
            inkscape_tagrefs = node.findall(
                "inkscape:tag/inkscape:tagref", namespaces=inkex.NSS)
        except TypeError:
            # fallback for lxml < 2.3.0
            path = 'inkscape:tag/inkscape:tagref'
            inkscape_tagrefs = node.xpath(path, namespaces=inkex.NSS)
        return inkscape_tagrefs

    def has_tagrefs(self):
        """Check whether document has selection sets with tagrefs."""
        defs = get_defs(self.document.getroot())
        return True if len(self.get_tagrefs(defs)) else False

    def update_tagrefs(self, mode='purge'):
        """Check tagrefs for deleted objects."""
        defs = get_defs(self.document.getroot())
        inkscape_tagrefs = self.get_tagrefs(defs)
        if len(inkscape_tagrefs):
            for tagref in inkscape_tagrefs:
                href = tagref.get(inkex.addNS('href', 'xlink'))[1:]
                if self.getElementById(href) is None:
                    if mode == 'purge':
                        tagref.getparent().remove(tagref)
                    elif mode == 'placeholder':
                        temp = inkex.etree.Element(inkex.addNS('path', 'svg'))
                        temp.set('id', href)
                        temp.set('d', 'M 0,0 Z')
                        self.document.getroot().append(temp)

    # ----- workaround to fix Effect() performance with large selections

    def collect_ids(self, doc=None):
        """Iterate all elements, build id dicts (doc_ids, selected)."""
        doc = self.document if doc is None else doc
        id_list = list(self.options.ids)
        for node in doc.getroot().iter(tag=inkex.etree.Element):
            if 'id' in node.attrib:
                node_id = node.get('id')
                self.doc_ids[node_id] = 1
                if node_id in id_list:
                    self.selected[node_id] = node
                    id_list.remove(node_id)

    def getselected(self):
        """Overload Effect() method."""
        self.collect_ids()

    def getdocids(self):
        """Overload Effect() method."""
        pass


if __name__ == '__main__':
    ME = PathOps()
    ME.affect()

# vim: et shiftwidth=4 tabstop=8 softtabstop=4 fileencoding=utf-8 textwidth=79
