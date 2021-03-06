'''
Main interface to Basis Set Exchange functionality
'''

import datetime
import json
import os
import textwrap

from . import compose
from . import converters
from . import fileio
from . import lut
from . import manip
from . import memo
from . import notes
from . import refconverters
from . import references

# Determine the path to the data directory that is part
# of this installation
_my_dir = os.path.dirname(os.path.abspath(__file__))
_default_data_dir = os.path.join(_my_dir, 'data')
_default_schema_dir = os.path.join(_my_dir, 'schema')

# Main URL of the project
_main_url = 'http://bse.pnl.gov'

# If set to True, memoization of some internal functions
# will be used. Generally safe to leave enabled - it
# won't use that much memory
memoize_enabled = True


def _convert_element_list(elements):
    '''Convert a list of elements to an internal list

    A list of elements can contain both integers and strings.
    This converts the list entirely to strings containing integer
    Z-numbers
    '''

    ret = []
    for el in elements:
        if isinstance(el, int):
            ret.append(str(el))
        elif isinstance(el, str) and not el.isdecimal():
            ret.append(str(lut.element_Z_from_sym(el)))
        else:
            ret.append(el)

    return ret


def _convert_version(ver):
    '''Convert a version to a string

    Versions can be either integers or strings.
    '''

    if isinstance(ver, int):
        return str(ver)
    else:
        return ver


def _get_basis_metadata(name, data_dir):
    '''Get metadata for a single basis set

    If the basis doesn't exist, an exception is raised
    '''

    # Transform the name into an internal representation
    tr_name = transform_basis_name(name)

    # Get the metadata for all basis sets
    metadata = get_metadata(data_dir)

    if not tr_name in metadata:
        raise KeyError("Basis set {} does not exist".format(name))

    return metadata[tr_name]


def transform_basis_name(name):
    """
    Transforms the name of a basis set to an internal representation

    This makes comparison of basis set names easier by, for example,
    converting the name to all lower case.
    """

    return name.lower()


def _header_string(comment_str):
    '''Creates a string that is placed ahead of many outputs
    '''

    dt = datetime.datetime.utcnow()
    timestamp = dt.strftime('%Y-%m-%d %H:%M:%S UTC')

    header = comment_str + '-' * 70 + '\n'
    header += comment_str + ' Basis Set Exchange\n'
    header += comment_str + ' ' + _main_url + '\n'
    header += comment_str + ' Accessed ' + timestamp + '\n'
    header += comment_str + '-' * 70 + '\n'

    return header


def _header_string_basis(basis_dict, comment_str):
    '''Creates a header with information about a basis set

    Information includes description, revision, etc, but not references
    '''

    tw = textwrap.TextWrapper(initial_indent='', subsequent_indent=comment_str + ' ' * 20)
    header = _header_string(comment_str)
    header += comment_str + '   Basis set: ' + basis_dict['basis_set_name'] + '\n'
    header += tw.fill(comment_str + ' Description: ' + basis_dict['basis_set_description']) + '\n'
    header += comment_str + '        Role: ' + basis_dict['basis_set_role'] + '\n'
    header += tw.fill(comment_str + '     Version: {}  ({})'.format(
        basis_dict['basis_set_version'], basis_dict['basis_set_revision_description'])) + '\n'
    header += comment_str + '-' * 70 + '\n'

    return header


def get_basis(name,
              elements=None,
              version=None,
              fmt=None,
              uncontract_general=False,
              uncontract_spdf=False,
              uncontract_segmented=False,
              make_general=False,
              optimize_general=False,
              data_dir=None,
              header=True):
    '''Obtain a basis set

    This is the main function for getting basis set information.
    This function reads in all the basis data and returns it either
    as a string or as a python dictionary.

    Parameters
    ----------
    name : str
        Name of the basis set. This is not case sensitive.
    elements : list
        List of elements that you want the basis set for. By default,
        all elements for which the basis set is defined are included.
        Elements can be specified by Z-number (int or str) or by symbol (str)
    version : int or str
        Obtain a specific version of this basis set. By default,
        the latest version is returned.
    fmt: str
        What format to return the basis set as. By defaut,
        basis set information is returned as a python dictionary. Otherwise,
        if a format is specified, a string is returned.
        Use :func:`bse.api.get_formats` to obtain the available formats.
    uncontract_general : bool
        If True, remove general contractions by duplicating the set
        of primitive exponents with each vector of coefficients.
        Primitives with zero coefficient are removed, as are duplicate shells.
    uncontract_spdf : bool
        If True, remove general contractions with combined angular momentum (sp, spd, etc)
        by duplicating the set of primitive exponents with each vector of coefficients.
        Primitives with zero coefficient are removed, as are duplicate shells.
    uncontract_segmented : bool
        If True, remove segmented contractions by duplicating each primitive into new shells.
        Each coefficient is set to 1.0
    make_general : bool
        If True, make the basis set as generally-contracted as possible. There will be one
        shell per angular momentum (for each element)
    optimize_general : bool
        Optimize by removing general contractions that contain uncontracted
        functions (see :func:`bse.manip.optimize_general`)
    data_dir : str
        Data directory with all the basis set information. By default,
        it is in the 'data' subdirectory of this project.
    '''

    data_dir = _default_data_dir if data_dir is None else data_dir
    bs_data = _get_basis_metadata(name, data_dir)

    # If version is not specified, use the latest
    if version is None:
        version = bs_data['latest_version']
    else:
        version = _convert_version(version)

    # Compose the entire basis set (all elements)
    table_file_name = '{}.{}.table.json'.format(bs_data['filebase'], version)
    table_file_path = os.path.join(data_dir, table_file_name)
    basis_dict = compose.compose_table_basis(table_file_path)

    # Handle optional arguments
    if elements is not None:
        # Convert to purely a list of strings tath represent integers
        elements = _convert_element_list(elements)

        bs_elements = basis_dict['basis_set_elements']

        # Are elements part of this basis set?
        for el in elements:
            if not el in bs_elements:
                raise KeyError("Element {} not found in basis {}".format(el, name))

            # Set to only the elements we want
            basis_dict['basis_set_elements'] = {k: v for k, v in bs_elements.items() if k in elements}

    if optimize_general:
        basis_dict = manip.optimize_general(basis_dict)
    if uncontract_general:
        basis_dict = manip.uncontract_general(basis_dict)
    if uncontract_spdf:
        basis_dict = manip.uncontract_spdf(basis_dict)
    if uncontract_segmented:
        basis_dict = manip.uncontract_segmented(basis_dict)
    if make_general:
        basis_dict = manip.make_general(basis_dict)

    # If fmt is not specified, return as a python dict
    if fmt is None:
        return basis_dict

    # make converters case insensitive
    fmt = fmt.lower()
    if fmt in converters.converter_map:
        ret_str = converters.converter_map[fmt]['function'](basis_dict)
    else:
        raise RuntimeError('Unknown basis set format "{}"'.format(fmt))

    if header and fmt != 'json':
        comment_str = converters.converter_map[fmt]['comment']
        ret_str = _header_string_basis(basis_dict, comment_str) + '\n\n' + ret_str

    # HACK - Psi4 requires the first non-comment line be spherical/cartesian
    #        so we have to add that before the header
    if fmt == 'psi4':
        ret_str = basis_dict['basis_set_harmonic_type'] + '\n\n' + ret_str

    return ret_str


def lookup_basis_by_role(primary_basis, role, data_dir=None):
    '''Lookup the name of a basis set given a primary basis set and role
    '''

    data_dir = _default_data_dir if data_dir is None else data_dir
    bs_data = _get_basis_metadata(primary_basis, data_dir)
    auxdata = bs_data['auxiliaries']

    if not role in auxdata:
        raise RuntimeError("Role {} doesn't exist for {}".format(role, primary_basis))

    return auxdata[role]


@memo.BSEMemoize
def get_metadata(data_dir=None):
    '''Obtain the metadata for all basis sets

    The metadata includes information such as the display name of the basis set,
    its versions, and what elements are included in the basis set

    The data is read from the METADATA.json file in the `data_dir` directory.

    Parameters
    ----------
    data_dir : str
        Data directory with all the basis set information. By default,
        it is in the 'data' subdirectory of this project.
    '''

    data_dir = _default_data_dir if data_dir is None else data_dir
    metadata_file = os.path.join(data_dir, "METADATA.json")
    return fileio.read_metadata(metadata_file)


@memo.BSEMemoize
def get_reference_data(data_dir=None):
    '''Obtain information for all stored references

    This is a nested dictionary with all the data for all the references

    The reference data is read from the REFERENCES.json file in the given
    `data_dir` directory.
    '''

    data_dir = _default_data_dir if data_dir is None else data_dir
    reffile_path = os.path.join(data_dir, 'REFERENCES.json')

    return fileio.read_references(reffile_path)


def get_all_basis_names(data_dir=None):
    '''Obtain a list of all basis set names

    The returned list is the internal representation of the basis set name.

    The data is read from the METADATA.json file in the data directory.

    Parameters
    ----------
    data_dir : str
        Data directory with all the basis set information. By default,
        it is in the 'data' subdirectory of this project.
    '''

    return sorted(list(get_metadata(data_dir).keys()))


def get_references(name, elements=None, version=None, fmt=None, data_dir=None):
    '''Get the references/citations for a basis set

    Parameters
    ----------
    name : str
        Name of the basis set. This is not case sensitive.
    elements : list
        List of element numbers that you want the basis set for. By default,
        all elements for which the basis set is defined are included.
    version : int
        Obtain a specific version of this basis set. By default,
        the latest version is returned.
    fmt: str
        What format to return the basis set as. By defaut,
        basis set information is returned as a list of dictionaries. Use
        get_reference_formats() to obtain the available formats.
    data_dir : str
        Data directory with all the basis set information. By default,
        it is in the 'data' subdirectory of this project.
    '''

    data_dir = _default_data_dir if data_dir is None else data_dir
    basis_dict = get_basis(name, elements=elements, version=version, data_dir=data_dir)

    all_ref_data = get_reference_data(data_dir)
    ref_data = references.compact_references(basis_dict, all_ref_data)

    if fmt is None:
        return ref_data

    # Make fmt case insensitive
    fmt = fmt.lower()
    if fmt in refconverters.converter_map:
        return refconverters.converter_map[fmt]['function'](ref_data)
    else:
        raise RuntimeError('Unknown reference format "{}"'.format(fmt))

    return ref_data


def get_basis_family(name, data_dir=None):
    '''Lookup a family by a basis set name
    '''

    data_dir = _default_data_dir if data_dir is None else data_dir
    bs_data = _get_basis_metadata(name, data_dir)
    return bs_data['family']


@memo.BSEMemoize
def get_family_notes(family, data_dir=None):
    '''Return a string representing the notes about a basis set family
    
    If the notes are not found, a string saying so is returned
    '''

    data_dir = _default_data_dir if data_dir is None else data_dir
    file_name = 'NOTES.' + family.lower()
    file_path = os.path.join(data_dir, file_name)

    notes_str = fileio.read_notes_file(file_path)
    if notes_str is None:
        notes_str = "Notes are not available for the {} family".format(family)

    ref_data = get_reference_data(data_dir)
    return notes.process_notes(notes_str, ref_data)


@memo.BSEMemoize
def get_basis_notes(name, data_dir=None):
    '''Return a string representing the notes about a specific basis set
    
    If the notes are not found, a string saying so is returned
    '''

    data_dir = _default_data_dir if data_dir is None else data_dir
    bs_data = _get_basis_metadata(name, data_dir)

    # the notes file is the same as the base file name, with a .notes extension
    file_name = bs_data['filebase'] + '.notes'
    file_path = os.path.join(data_dir, file_name)

    notes_str = fileio.read_notes_file(file_path)
    if notes_str is None:
        notes_str = "Notes are not available for the {} basis".format(name)

    ref_data = get_reference_data(data_dir)
    return notes.process_notes(notes_str, ref_data)


def get_schema(schema_type):
    '''Get a schema that can validate BSE JSON files

       The schema_type represents the type of BSE JSON file to be validated,
       and can be 'component', 'element', 'table', or 'references'.
    '''

    schema_file = "{}-schema.json".format(schema_type)
    file_path = os.path.join(_default_schema_dir, schema_file)

    if not os.path.isfile(file_path):
        raise RuntimeError('Schema file \'{}\' does not exist, is not readable, or is not a file'.format(file_path))

    return fileio.read_schema(file_path)


def get_formats():
    '''Return information about the basis set formats available

    The returned data is a map of format to display name. The format
    can be passed as the fmt argument to :func:`get_basis()`
    '''
    return {k: v['display'] for k, v in converters.converter_map.items()}


def get_reference_formats():
    '''Return information about the reference/citation formats available

    The returned data is a map of format to display name. The format
    can be passed as the fmt argument to :func:`get_references`
    '''
    return {k: v['display'] for k, v in refconverters.converter_map.items()}
