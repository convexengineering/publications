from gpkit import Model, Variable, SignomialsEnabled, SignomialEquality, VarKey, units,Vectorize
from gpkit.constraints.bounded import Bounded
from relaxed_constants import relaxed_constants, post_process

import numpy as np
import matplotlib.pyplot as plt

from SimPleAC_mission4 import Mission, SimPleAC
from atmosphere import Atmosphere

class Multimission(Model):
    def setup(self,Nmissions,Nsegments):
        self.aircraft = SimPleAC()
        self.missions = []
        for i in range(0,Nmissions):
            self.missions.append(Mission(self.aircraft,Nsegments))

        # Multimission objective variables
        W_f_mm = Variable('W_{f_{mm}}','N','Multimission fuel weight')

        with Vectorize(Nmissions):
            # Mission variables
            hcruise    = Variable('h_{cruise_{mm}}', 'm', 'minimum cruise altitude')
            Range      = Variable("Range_{mm}", "km", "aircraft range")
            W_p        = Variable("W_{p_{mm}}", "N", "payload weight", pr=20.)
            V_min      = Variable("V_{min_{mm}}", 25, "m/s", "takeoff speed", pr=20.)
            cost_index = Variable("C_{mm}", '1/hr','hourly cost index')
            TOfac      = Variable('T/O factor_{mm}', 2.,'-','takeoff thrust factor')

        constraints = []

        # Setting up the missions
        for i in range(0,Nmissions):
            constraints += [
            self.missions[i]['h_{cruise_m}'] == hcruise[i],
            self.missions[i]['Range_m']      == Range[i],
            self.missions[i]['W_{p_m}']        == W_p[i],
            self.missions[i]['V_{min_m}']    == V_min[i],
            self.missions[i]['C_m']          == cost_index[i],
            self.missions[i]['T/O factor_m'] == TOfac[i],
            # Upper bounding relevant variables
            W_f_mm <= 1e11*units('N'),
            ]

        # Multimission constraints
        constraints += [W_f_mm >= sum(self.missions[i]['W_{f_m}'] for i in range(0,Nmissions))]



        return constraints, self.aircraft, self.missions

if __name__ == "__main__":
    Nmissions = 2
    Nsegments = 5
    m = Multimission(Nmissions,Nsegments)
    m.substitutions.update({
        'h_{cruise_{mm}}':[5000*units('m'), 5000*units('m')],
        'Range_{mm}'     :[3000*units('km'), 2000*units('km')],
        'W_{p_{mm}}'     :[6250*units('N'),   8000*units('N')],
        'C_{mm}'         :[120*units('1/hr'), 360*units('1/hr')],
    })
    #m.cost = m['W_{f_{mm}}']*units('1/N') + sum(m.missions[i]['C_m']*m.missions[i]['t_m'] for i in range(0,Nmissions))
    m.cost = (m.missions[0]['W_{f_m}']*units('1/N') + m.missions[1]['C_m']*m.missions[1]['t_m'])
    sol = m.localsolve(verbosity = 4)

