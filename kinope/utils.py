"""
utils.py
miscellaneous utilities
"""
from simtk import unit
from simtk import openmm


def serialize(item, filename):
    """
    Serialize an OpenMM System, State, or Integrator.

    Parameters
    ----------
    item : System, State, or Integrator
        The thing to be serialized
    filename : str
        The filename to serialize to
    """
    from simtk.openmm import XmlSerializer
    if filename[-2:] == 'gz':
        import gzip
        with gzip.open(filename, 'wb') as outfile:
            serialized_thing = XmlSerializer.serialize(item)
            outfile.write(serialized_thing.encode())
    if filename[-3:] == 'bz2':
        import bz2
        with bz2.open(filename, 'wb') as outfile:
            serialized_thing = XmlSerializer.serialize(item)
            outfile.write(serialized_thing.encode())
    else:
        with open(filename, 'w') as outfile:
            serialized_thing = XmlSerializer.serialize(item)
            outfile.write(serialized_thing)

def make_core_file(numSteps,
                   xtcFreq,
                   globalVarFreq,
                   xtcAtoms,
                   precision='mixed',
                   globalVarFilename='globals.csv',
                   directory='.'):
    """ Makes core.xml file for simulating on folding at home
    Parameters
    ----------
    numSteps : int
        Number of steps to perform
    xtcFreq : int
        Frequency to save configuration to disk
    globalVarFreq : int
        Frequency to save variables to globalVarFilename
    xtcAtoms : str, default='solute'
        Which atoms to save
    precision : str, default='mixed'
        Precision of simulation
    globalVarFilename : str, default='globals.csv'
        Filename to store global simulation results
    directory : str, default='.'
        Location on disk to save core.xml file
    # TODO - unhardcode 'core.xml' or would it always be this?
    """
    core_parameters = {
        'numSteps': numSteps,
        'xtcFreq': xtcFreq,
        'xtcAtoms': xtcAtoms,
        'precision': precision,
        'globalVarFilename': globalVarFilename,
        'globalVarFreq': globalVarFreq,
    }
    # Serialize core.xml
    import dicttoxml
    with open(f'{directory}/core.xml', 'wt') as outfile:
        #core_parameters = create_core_parameters(phase)
        xml = dicttoxml.dicttoxml(core_parameters, custom_root='config', attr_type=False)
        from xml.dom.minidom import parseString
        dom = parseString(xml)
        outfile.write(dom.toprettyxml())

def deserialize_xml(xml_filename):
    """
    load and deserialize an xml
    arguments
        xml_filename : str
            full path of the xml filename
    returns
        xml_deserialized : deserialized xml object
    """
    from simtk.openmm.openmm import XmlSerializer
    with open(xml_filename, 'r') as infile:
        xml_readable = infile.read()
    xml_deserialized = XmlSerializer.deserialize(xml_readable)
    return xml_deserialized
