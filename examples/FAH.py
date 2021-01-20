"""
demonstrate how to create fah-amenable (serialized) systems, integrators, states, and core files

FAH.py
"""

"""
Suppose I have a system (with positions and perhaps box vectors) which I want to prepare and run on FAH.

In this particular demonstration, I will show how to serialize an xml for periodic nonequilibrium simulations
with a rest-enabled system (see kinope/tempering.RESTFactory)

>>> #imports
>>> from openmmtools.states import SamplerState
>>> from openmmtools.integrators import PeriodicNonequilibriumIntegrator
>>> from simtk import unit, openmm
>>> from kinope.tempering import RESTFactory

>>> #constants
>>> temperature = 300*unit.kelvin #target temperature
>>> T_max = 1200*unit.kelvin #high temperature target (this is a free parameter)
>>> pressure=1.0*unit.atmosphere
>>> barostat_freq=50

>>> #make the rest factory
>>> solute_region = range(5) #my solute region will be the first 5 particles in the system
>>> system.addForce(openmm.MonteCarloBarostat(pressure, temperature, barostat_freq)) #add this if the system doesnt have a barostat and needs one
>>> factory = RESTFactory(system=system, solute_region=solute_region) #equip the system and the solute region
>>> rest_system = factory.REST_system
>>> protocol_dict = factory.get_protocol(T_min=temperature/unit.kelvin, T_max=T_max/unit.kelvin) #specify the target and max temperature (unitless) to generate the protocol
>>> samplerstate = SamplerState(positions, box_vectors=system.getDefaultPeriodicBoxVectors())

>>> #make a nonequilibrium integrator, state, and context
>>> nsteps_neq = 250000 # @4.0 fs timesteps gives 1ns per nonequilibrium heating/cooling switch (or half a ns heating and half a ns cooling)
>>> nsteps_eq = 500000 # @4.0 fs timesteps gives 2ns equilibration before/after heating/cooling protocol
>>> neq_integrator = PeriodicNonequilibriumIntegrator(temperature=temperature, collision_rate = 1./unit.picoseconds, timestep=4.0*unit.femtoseconds, alchemical_functions=protocol_dict, splitting="V R H O R V", nsteps_eq=nsteps_eq, nsteps_neq=nsteps_neq)
>>> context = openmm.Context(rest_system, neq_integrator) #equip the system and its integrator, let it default to fastest platform
>>> samplerstate.apply_to_context(context) #apply the positions and box vectors to the context
>>> context.setVelocitiesToTemperature(temperature)
>>> state = context.getState(getDataTypes=True,getForces=True, getParameters=True, getPeriodicBoxVectors=True, getPositions=True, getVelocities=True)

you can serialize and save the state, context, system, and core files with the functions in kinope.utils.

NOTE : there are several user-defined parameters in the scheme of nonequilibrium tempering.
Essentially, what the integrator will do is the following:
    1. run nsteps_eq at lambda 0 (target temperature equilibrium dynamics with a "V R O R V" Langevin integrator with the given timestep/collision_rate, etc)
    2. anneal from lambda=0 to 1 over nsteps_neq (heating over the `protocol_dict` schedule from lambda=0 to 0.5, and cooling back to target temperature from lambda=0.5 to 1)
    3. run nsteps_eq at the lambda 1 endstate (target temperature, s.t. lambda 0 and 1 define the _same_ distribution)
    4. anneal back to lambda 0 (same as 2)
    5. repeat 1-4
if you are interested in doing free energy calculations (reorganizational free energy about heating/cooling schedules)
you will want to save the configuration (of the atoms you are interested in) at step nsteps_eq, nsteps_eq + nsteps_neq, 2*nsteps_eq + nsteps_neq, 2*(nsteps_eq + nsteps_neq), etc.
(i.e. you want to save configurations at the start and end of every nonequilibrium switch).
Also, you will want to save the `protocol_work` variable in the `PeriodicNonequilibriumIntegrator` after every nonequlibrium switch since you need to
compute the work put into the system during the lambda schedule.

NOTE : this is experimental and can potentially be buggy. please inform me of bugs you encounter.
"""
