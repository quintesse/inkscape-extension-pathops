# inx-pathops

Inkscape extension to apply a path operation multiple times to a
selection of objects.


## Basic Usage

This extension takes a selection of one or more groups, or of several
elements (paths, shapes, text), or a mix of both, and applies a chosen
path operation with the top-most valid object in paint order and each
other valid object which is part of the selection (directly or as member
of a processed group) that is lower in Z-order.

Objects which are considered "valid" for path operations:
- paths
- shapes
- text

Other graphic elements like clones or bitmap images are silently ignored.


## Options

### Max operations per run
Large selections with a high count of valid objects are supported by
processing the path operations in chunks. The number of operations to be
maximally applied per externally spawned command can be configured by
the user.  The current default is 500.  Note that the actual limit
(length of the list of arguments for external command) is OS-dependent
and could be higher (Linux, OS X) or lower (probably on Windows).

### Recurse into groups
Groups in the selection are handled transparently: the ids of the
contained objects are collected and checked; unsupported object types
(e.g. clones, or bitmap images) are silently dropped from the list. With
default settings, the support for nested group levels is unlimited. It
can optionally be reduced to 1 to process only the direct members of the
top-level groups in the selection, without further recursion.

### Keep top element when done
The top-most path by default is retained after the path operations, and
can optionally be removed once all path operations are done.

### Dry run
If checked, the extension processes the selection and returns
information about object count, chunk size and the assembled argument
lists for the external commands without actually executing them.

### Shortcuts
The defaults for the individual PathOps extensions which don't show a
dialog:
- Max. operations per external command: 500
- Recurse into groups
- Keep top-most object
- No dry-run


## Installation

Copy the files in the `src/` directory into the user extensions
directory (see 'Inkscape Preferences > System' for the exact location)
and relaunch Inkscape.

### The extensions will be available as:

**Extensions > Generate from Path:**
- PathOps Custom...

**Extensions > Generate from Path > PathOps:**
- 1 Union
- 2 Difference
- 3 Intersection
- 4 Exclusion
- 5 Division
- 6 Cut Path
- 7 Combine


## Background

**inx-pathops** is a rewrite of an extension originally authored by Ryan
Lerch
([**inkscape-extension-multiple-difference**](https://github.com/ryanlerch/inkscape-extension-multiple-difference))
and later expanded in a fork by Maren Hachmann
([**inkscape-extensions-multi-bool**](https://gitlab.com/Moini/inkscape-extensions-multi-bool)).

The rewrite started with the interest to improve overall performance:
* **Responsiveness**  
Support for groups (one level, or unlimited nested levels) was
implemented, which can reduce response times because a large number of
elements can be passed from inkscape to the extension script with just
the reference to the id(s) of one or several selected group(s).  
Additionally, a time-consuming method provided in a module shared by
Inkscape to pre-process the objects in the selection has been identified
and is overloaded with a faster method.
* **Z-sorted list** of elements  
The Z-sorting of the selected elements to be processed is done
internally in python (initially with zSort from pathmodifier, now
rewritten as function that returns an iterator) instead of spawning a
separate inkscape process to query all drawing content.
* **OSError: `Argument list too long`**  
Applying the path operation on a huge number of elements creates a
command with a long list of arguments to spawn a second inkscape
process. This can hit OS-dependent limits and cause the extension to
fail. ***inx-pathops*** splits the list of elements into smaller
'chunks' (based on a user-defined max count), and spawns a series of
inkscape commands, one for each chunk.
* **Maintenance**  
A single python script and several INX files are used to provide access
to the supported path operations. ***inx-pathops*** offers a combined
dialog with additional options, as well as a separate INX file for each
path operation which allows direct application without a dialog (each
can be assigned a custom keyboard shortcut if frequently used).


## Source

The extension is developed and maintained in:  
https://gitlab.com/su-v/inx-pathops

A ZIP archive of recent snapshot also be downloaded here:  
https://gitlab.com/su-v/inx-pathops/tags


## License

GPL-2+
