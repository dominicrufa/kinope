"""
test_tempering.py
"""
import numpy as np
from simtk import unit, openmm

def make_ala_explicit_REST(pressure=1.0*unit.atmosphere,
                           temperature=300.0*unit.kelvin,
                           barostat_freq=50,
                           REST_kwarg_dict = {
                                              'solute_region': range(5),
                                              'use_dispersion_correction': True}
                                              ):
    """
    make an explicit alanine dipeptide with REST
    """
    from openmmtools.testsystems import AlanineDipeptideExplicit
    from kinope.tempering import RESTFactory

    ala = AlanineDipeptideExplicit(use_dispersion_correction=False)
    ala.system.removeForce(4) #remove CMMMotion

    barostat = openmm.MonteCarloBarostat(pressure, temperature, barostat_freq)
    ala.system.addForce(barostat)

    #REST the system
    factory = RESTFactory(system=ala.system, **REST_kwarg_dict)

    return ala, factory

def test_RESTFactory():
    """
    create an explicit alanine dipeptide in solvent, create a rest system, and assert the zeroth temperatures scale;
    """
    from openmmtools.states import ThermodynamicState, SamplerState
    from openmmtools.integrators import DummyIntegrator
    from openmmtools.constants import kB
    kT = kB*300*unit.kelvin
    ala, rest_factory = make_ala_explicit_REST()
    rest_system = rest_factory.REST_system

    og_system = rest_factory._og_system

    og_thermostate = ThermodynamicState(og_system, temperature=300*unit.kelvin)
    rest_thermostate = ThermodynamicState(rest_system, temperature=300*unit.kelvin)

    sampler_state = SamplerState(ala.positions, box_vectors=og_system.getDefaultPeriodicBoxVectors())

    og_dummy_int, rest_dummy_int = DummyIntegrator(), DummyIntegrator()

    og_context, rest_context = og_thermostate.create_context(og_dummy_int), rest_thermostate.create_context(rest_dummy_int)

    sampler_state.apply_to_context(og_context)
    sampler_state.apply_to_context(rest_context)

    og_state = og_context.getState(getEnergy=True)
    rest_state = rest_context.getState(getEnergy=True)

    og_pe, rest_pe = og_state.getPotentialEnergy()/kT, rest_state.getPotentialEnergy()/kT
    print(og_pe)
    print(rest_pe)
    assert np.isclose(og_pe - rest_pe, 0., atol=1e-4), f"there is a discrepancy between the og system E ({og_pe}) and the rest system E ({rest_pe})"
