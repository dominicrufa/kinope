"""
tempering.py
create a REST-enabled system
"""

#IMPORTS
import simtk.openmm as openmm
import simtk.unit as unit
import mdtraj as md
import numpy as np
import copy
import enum
import itertools

#######LOGGING#############################
import logging
logging.basicConfig(level = logging.NOTSET)
_logger = logging.getLogger("temper")
_logger.setLevel(logging.INFO)
###########################################

class RESTFactory(object):
    """
    This class takes a standard simtk.openmm.system equipped with
        a. `HarmonicBondForce`
        b. `HarmonicAngleForce`
        c. `PeriodicTorsionForce`
        d. `NonbondedForce`
        e. `MonteCarloBarostat` (for LangevinIntegrator)
    and will convert to another system that is equipped with the necessary global variables and perDOF variables
    to conduct targeted heating/cooling of a specified 'solute region'
    """
    _known_forces = {'HarmonicBondForce', 'HarmonicAngleForce', 'PeriodicTorsionForce', 'NonbondedForce', 'MonteCarloBarostat'}

    def __init__(self, system, solute_region, use_dispersion_correction=False, **kwargs):
        """
        arguments
            system : simtk.openmm.system
                system that will be rewritten
            solute_region : simtk.openmm.system
                subset solute region
            use_dispersion_correction : bool, default False
                whether to use a dispersion correction
        Properties
        ----------
            REST_system : simtk.openmm.system
                the REST2-implemented system
        """
        self._use_dispersion_correction = use_dispersion_correction
        self._num_particles = system.getNumParticles()
        self._og_system = system
        self._og_system_forces = {type(force).__name__ : force for force in self._og_system.getForces()}
        self._out_system_forces = {}
        self._solute_region = solute_region
        self._solvent_region = list(set(range(self._num_particles)).difference(set(self._solute_region)))
        self._global_params = []
        _logger.debug(f"solvent region: {self._solvent_region}")
        _logger.debug(f"solute region: {self._solute_region}")


        assert set(solute_region).issubset(set(range(self._num_particles))), f"the solute region is not a subset of the system particles"
        self._nonbonded_method = self._og_system_forces['NonbondedForce'].getNonbondedMethod()
        self._out_system = openmm.System()

        for particle_idx in range(self._num_particles):
            particle_mass = self._og_system.getParticleMass(particle_idx)
            hybrid_idx = self._out_system.addParticle(particle_mass)

        if "MonteCarloBarostat" in self._og_system_forces.keys():
            barostat = copy.deepcopy(self._og_system_forces["MonteCarloBarostat"])
            self._out_system.addForce(barostat)
            self._out_system_forces[barostat.__class__.__name__] = barostat
            _logger.info("Added MonteCarloBarostat.")
        else:
            _logger.info("No MonteCarloBarostat added.")

        # Copy over the box vectors:
        box_vectors = self._og_system.getDefaultPeriodicBoxVectors()
        self._out_system.setDefaultPeriodicBoxVectors(*box_vectors)
        _logger.info(f"getDefaultPeriodicBoxVectors added to hybrid: {box_vectors}")


        # Check that there are no unknown forces in the new and old systems:
        for system_name in ['og']:
            force_names = getattr(self, '_{}_system_forces'.format(system_name)).keys()
            unknown_forces = set(force_names) - set(self._known_forces)
            if len(unknown_forces) > 0:
                raise ValueError(f"Unknown forces {unknown_forces} encountered in {system_name} system")
        _logger.info("No unknown forces.")

        self._handle_constraints()

        self._add_bond_force_terms()
        self._add_bonds()

        self._add_angle_force_terms()
        self._add_angles()

        self._add_torsion_force_terms()
        self._add_torsions()

        self._add_nonbonded_force_terms()
        self._add_nonbondeds()

    def _handle_constraints(self):
        for constraint_idx in range(self._og_system.getNumConstraints()):
            atom1, atom2, length = self._og_system.getConstraintParameters(constraint_idx)
            self._out_system.addConstraint(atom1, atom2, length)

    def _add_bond_force_terms(self):
        core_energy_expression = '(K/2)*(r-length)^2;'
        core_energy_expression += 'K = k*scale_factor;' # linearly interpolate spring constant
        core_energy_expression += self.scaling_expression()

        # Create the force and add the relevant parameters
        custom_core_force = openmm.CustomBondForce(core_energy_expression)
        custom_core_force.addPerBondParameter('length')
        custom_core_force.addPerBondParameter('k')
        custom_core_force.addPerBondParameter('identifier')

        for q in ['solute_scale', 'inter_scale']:
            custom_core_force.addGlobalParameter(q, 1.0)
            self._global_params.append(q)

        self._out_system.addForce(custom_core_force)
        self._out_system_forces[custom_core_force.__class__.__name__] = custom_core_force

    def scaling_expression(self, nb=False):
        if not nb:
            last_line = '_is_solute = delta(identifier); _is_solvent = delta(1-identifier); _is_inter = delta(2-identifier);'
        else:
            last_line = '_is_solute = delta(identifier1 + identifier2); _is_solvent = delta(2 - (identifier1 + identifier2)); _is_inter = delta(1 - (identifier1 + identifier2));'

        out = f"scale_factor = solute_scale*_is_solute + solvent_scale*_is_solvent + inter_scale*_is_inter; \
               solvent_scale = 1.; \
               {last_line} \
               "
        return out

    def _add_angle_force_terms(self):
        core_energy_expression = '(K/2)*(theta-theta0)^2;'
        core_energy_expression += 'K = k*scale_factor;' # linearly interpolate spring constant
        core_energy_expression += self.scaling_expression()

        # Create the force and add the relevant parameters
        custom_core_force = openmm.CustomAngleForce(core_energy_expression)
        custom_core_force.addPerAngleParameter('theta0')
        custom_core_force.addPerAngleParameter('k')
        custom_core_force.addPerAngleParameter('identifier')

        for q in ['solute_scale', 'inter_scale']:
            custom_core_force.addGlobalParameter(q, 1.0)
            self._global_params.append(q)

        self._out_system.addForce(custom_core_force)
        self._out_system_forces[custom_core_force.__class__.__name__] = custom_core_force

    def _add_torsion_force_terms(self):
        core_energy_expression = 'K*(1+cos(periodicity*theta-phase));'
        core_energy_expression += 'K = k*scale_factor;' # linearly interpolate spring constant
        core_energy_expression += self.scaling_expression()

        # Create the force and add the relevant parameters
        custom_core_force = openmm.CustomTorsionForce(core_energy_expression)
        custom_core_force.addPerTorsionParameter('periodicity') # molecule1 periodicity
        custom_core_force.addPerTorsionParameter('phase') # molecule1 phase
        custom_core_force.addPerTorsionParameter('k') # molecule1 spring constant
        custom_core_force.addPerTorsionParameter('identifier')

        for q in ['solute_scale', 'inter_scale']:
            custom_core_force.addGlobalParameter(q, 1.0)
            self._global_params.append(q)

        self._out_system.addForce(custom_core_force)
        self._out_system_forces[custom_core_force.__class__.__name__] = custom_core_force

    def _add_nonbonded_force_terms(self):
        standard_nonbonded_force = openmm.NonbondedForce()
        self._out_system.addForce(standard_nonbonded_force)
        self._out_system_forces[standard_nonbonded_force.__class__.__name__] = standard_nonbonded_force

        #set the appropriate parameters
        epsilon_solvent = self._og_system_forces['NonbondedForce'].getReactionFieldDielectric()
        r_cutoff = self._og_system_forces['NonbondedForce'].getCutoffDistance()
        switch_bool = self._og_system_forces['NonbondedForce'].getUseSwitchingFunction()
        standard_nonbonded_force.setUseSwitchingFunction(switch_bool)
        if switch_bool:
            switching_distance = self._og_system_forces['NonbondedForce'].getSwitchingDistance()
            standard_nonbonded_force.setSwitchingDistance(switching_distance)

        if self._nonbonded_method != openmm.NonbondedForce.NoCutoff:
            standard_nonbonded_force.setReactionFieldDielectric(epsilon_solvent)
            standard_nonbonded_force.setCutoffDistance(r_cutoff)
        if self._nonbonded_method in [openmm.NonbondedForce.PME, openmm.NonbondedForce.Ewald]:
            [alpha_ewald, nx, ny, nz] = self._og_system_forces['NonbondedForce'].getPMEParameters()
            delta = self._og_system_forces['NonbondedForce'].getEwaldErrorTolerance()
            standard_nonbonded_force.setPMEParameters(alpha_ewald, nx, ny, nz)
            standard_nonbonded_force.setEwaldErrorTolerance(delta)
        standard_nonbonded_force.setNonbondedMethod(self._nonbonded_method)

        if self._og_system_forces['NonbondedForce'].getUseDispersionCorrection() and self._use_dispersion_correction:
            self._out_system_forces['NonbondedForce'].setUseDispersionCorrection(True)
        else:
            self._out_system_forces['NonbondedForce'].setUseDispersionCorrection(False)

        #add the global value
        for q in ['electrostatic_scale', 'steric_scale']:
            self._out_system_forces['NonbondedForce'].addGlobalParameter(q, 0.)
            self._global_params.append(q)


    def get_identifier(self, particles):
        if type(particles) == int:
            out = 0 if particles in self._solute_region else 1
            return out

        if all(x in self._solvent_region for x in particles):
            out = 1
        elif all(x in self._solute_region for x in particles):
            out = 0
        else:
            out = 2
        return out


    def _add_bonds(self):
        """
        add bonds
        """
        og_bond_force = self._og_system_forces['HarmonicBondForce']
        for bond_idx in range(og_bond_force.getNumBonds()):
            p1, p2, length, k = og_bond_force.getBondParameters(bond_idx)
            identifier = self.get_identifier([p1, p2])
            self._out_system_forces['CustomBondForce'].addBond(p1, p2, [length, k, identifier])

    def _add_angles(self):
        og_angle_force = self._og_system_forces['HarmonicAngleForce']
        for angle_idx in range(og_angle_force.getNumAngles()):
            p1, p2, p3, theta0, k = og_angle_force.getAngleParameters(angle_idx)
            identifier = self.get_identifier([p1, p2, p3])
            self._out_system_forces['CustomAngleForce'].addAngle(p1, p2, p3, [theta0, k, identifier])

    def _add_torsions(self):
        og_torsion_force = self._og_system_forces['PeriodicTorsionForce']
        for torsion_idx in range(og_torsion_force.getNumTorsions()):
            p1, p2, p3, p4, per, phase, k = og_torsion_force.getTorsionParameters(torsion_idx)
            identifier = self.get_identifier([p1, p2, p3, p4])
            self._out_system_forces['CustomTorsionForce'].addTorsion(p1, p2, p3, p4, [per, phase, k, identifier])

    def _add_nonbondeds(self):
        og_nb_force = self._og_system_forces['NonbondedForce']

        for particle_idx in range(self._num_particles):
            q, sigma, epsilon = og_nb_force.getParticleParameters(particle_idx)
            identifier = self.get_identifier(particle_idx)

            if identifier == 1: #solvent
                self._out_system_forces['NonbondedForce'].addParticle(q, sigma, epsilon)

            else: #solute
                self._out_system_forces['NonbondedForce'].addParticle(q, sigma, epsilon)
                self._out_system_forces['NonbondedForce'].addParticleParameterOffset('electrostatic_scale', particle_idx, q, 0.0*sigma, epsilon*0.0)
                self._out_system_forces['NonbondedForce'].addParticleParameterOffset('steric_scale', particle_idx, q*0.0, 0.0*sigma, epsilon)


        #handle exceptions
        for exception_idx in range(og_nb_force.getNumExceptions()):
            p1, p2, chargeProd, sigma, epsilon = og_nb_force.getExceptionParameters(exception_idx)
            identifier = self.get_identifier([p1, p2])
            exc_idx = self._out_system_forces['NonbondedForce'].addException(p1, p2, chargeProd, sigma, epsilon)
            if identifier == 1: #solvent
                pass
            elif identifier == 0: #solute
                self._out_system_forces['NonbondedForce'].addExceptionParameterOffset('steric_scale', exc_idx, chargeProd, 0.0*sigma, epsilon)

            elif identifier == 2: #inter
                self._out_system_forces['NonbondedForce'].addExceptionParameterOffset('electrostatic_scale', exc_idx, chargeProd, 0.0*sigma, epsilon)

    def get_protocol(self, T_min, T_max):
        """
        get a lambda-dependent alchemical protocol
        """
        exponand_1 = '(lambda)'
        exponand_2 = '(1.0 - lambda)'
        base_temperature_expression = "{T_min} + ({T_max} - {T_min})*(exp(2*{exponand}) - 1) / (exp(1) - 1)"
        temperature_expression = f"select(step(lambda - 0.5), {base_temperature_expression.format(T_min=T_min, T_max=T_max, exponand=exponand_2)}, {base_temperature_expression.format(T_min=T_min, T_max=T_max, exponand=exponand_1)})"

        unique_global_params = list(set(self._global_params))
        alchemical_dict = {'solute_scale': f"{T_min} / {temperature_expression}",
                           'inter_scale': f"sqrt({T_min} / {temperature_expression})",
                           'steric_scale': f"({T_min} / {temperature_expression}) - 1",
                           'electrostatic_scale': f"sqrt({T_min} / {temperature_expression}) - 1"
        }
        return alchemical_dict


    @property
    def REST_system(self):
        return self._out_system
