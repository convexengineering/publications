from gpkit import Model, Variable, SignomialsEnabled, SignomialEquality, VarKey, units,Vectorize
from gpkit.constraints.bounded import Bounded
from relaxed_constants import relaxed_constants, post_process

import numpy as np
import matplotlib.pyplot as plt

# Importing models
from atmosphere import Atmosphere

class SimPleAC(Model):
    def setup(self):
        self.engine = Engine()
        self.wing = Wing()
        self.fuse = Fuselage()
        self.components = [self.engine, self.wing, self.fuse]

        # Environmental constants
        g         = Variable("g", 9.81, "m/s^2", "gravitational acceleration")
        rho_f     = Variable("\\rho_f", 817, "kg/m^3", "density of fuel")

        # Free Variables
        W         = Variable("W", "N", "maximum takeoff weight")
        W_f       = Variable("W_f", "N", "maximum fuel weight")
        V_f       = Variable("V_f", "m^3", "maximum fuel volume")
        V_f_avail = Variable("V_{f_{avail}}", "m^3", "fuel volume available")

        constraints = []
  
        # Thrust and drag model
        constraints += [self.fuse['C_{D_{fuse}}'] == self.fuse['(CDA0)'] / self.wing['S']]

        # Fuel volume model 
        with SignomialsEnabled():
            constraints += [V_f == W_f / g / rho_f,
                    V_f_avail <= self.wing['V_{f_{wing}}'] + self.fuse['V_{f_{fuse}}'], #[SP]
                    V_f_avail >= V_f]

        return constraints, self.components

    def dynamic(self,state):
        return SimPleACP(self,state)

class SimPleACP(Model):
    def setup(self,aircraft,state):
        self.aircraft = aircraft
        self.engineP  = aircraft.engine.dynamic(state)
        self.wingP    = aircraft.wing.dynamic(state)
        self.Pmodels  = [self.engineP, self.wingP]

        # Free variables
        C_D       = Variable("C_D", "-", "drag coefficient")
        D         = Variable("D", "N", "total drag force")
        LoD       = Variable('L/D','-','lift-to-drag ratio')
        Re        = Variable("Re", "-", "Reynolds number")
        V         = Variable("V", "m/s", "cruising speed")

        constraints = []

        constraints += [self.engineP['T'] * V <= self.aircraft.engine['\\eta_{prop}'] * self.engineP['P_{shaft}'],
                    C_D >= self.aircraft['C_{D_{fuse}}'] + self.wingP['C_{D_{wpar}}'] + self.wingP['C_{D_{ind}}'],
                    D >= 0.5 * state['\\rho'] * self.aircraft['S'] * C_D * V ** 2,
                    Re == (state['\\rho'] / state['\\mu']) * V * (self.aircraft['S'] / self.aircraft['A']) ** 0.5,
                    self.wingP['C_f'] >= 0.074 / Re ** 0.2,
                    LoD == self.wingP['C_L'] / C_D]

        return constraints, self.Pmodels

class Fuselage(Model):
    def setup(self):
        # Free Variables
        CDA0      = Variable("(CDA0)", "m^2", "fuselage drag area") #0.035 originally
        C_D_fuse  = Variable('C_{D_{fuse}}','-','fuselage drag coefficient')
        # Free variables (fixed for performance eval.)
        V_f_fuse  = Variable('V_{f_{fuse}}','m^3','fuel volume in the fuselage', fix = True)

        constraints = []
        constraints += [V_f_fuse == 10*units('m')*CDA0,
                        V_f_fuse >= 1*10**-5*units('m^3')]

        return constraints

class Wing(Model):
    def setup(self):
        # Non-dimensional constants
        C_Lmax     = Variable("C_{L,max}", 1.6, "-", "lift coefficient at stall", pr=5.)
        e          = Variable("e", 0.92, "-", "Oswald efficiency factor", pr=3.)
        k          = Variable("k", 1.17, "-", "form factor", pr=10.)
        N_ult      = Variable("N_{ult}", 3.3, "-", "ultimate load factor", pr=15.)
        S_wetratio = Variable("(\\frac{S}{S_{wet}})", 2.075, "-", "wetted area ratio", pr=3.)
        tau        = Variable("\\tau", 0.12, "-", "airfoil thickness to chord ratio", pr=10.)

        # Dimensional constants
        W_w_coeff1 = Variable("W_{w_{coeff1}}", 2e-5, "1/m",
                              "wing weight coefficient 1", pr= 30.) #orig  12e-5
        W_w_coeff2 = Variable("W_{w_{coeff2}}", 60., "Pa",
                              "wing weight coefficient 2", pr=10.)

        # Free Variables (fixed for performance eval.)
        A         = Variable("A", "-", "aspect ratio",fix = True)
        S         = Variable("S", "m^2", "total wing area", fix = True)
        W_w       = Variable("W_w", "N", "wing weight")#, fix = True)
        W_w_strc  = Variable('W_{w_{strc}}','N','wing structural weight', fix = True)
        W_w_surf  = Variable('W_{w_{surf}}','N','wing skin weight', fix = True)
        V_f_wing  = Variable("V_{f_{wing}}",'m^3','fuel volume in the wing', fix = True)

        constraints = []

        # Structural model
        constraints += [W_w_surf >= W_w_coeff2 * S,
                        W_w >= W_w_surf + W_w_strc]

        # Wing fuel model
        constraints += [V_f_wing**2 <= 0.0009*S**3/A*tau**2] # linear with b and tau, quadratic with chord

        return constraints

    def dynamic(self,state):
        return WingP(self,state)

class WingP(Model):
    def setup(self,wing,state):
        self.wing = wing
        # Free Variables
        C_f       = Variable("C_f", "-", "skin friction coefficient")
        C_D_ind   = Variable('C_{D_{ind}}', '-', "wing induced drag")
        C_D_wpar  = Variable('C_{D_{wpar}}', '-', 'wing profile drag')
        C_L       = Variable("C_L", "-", "wing lift coefficient")

        constraints = []

        # Drag model
        constraints += [C_D_ind == C_L ** 2 / (np.pi * self.wing['A'] * self.wing['e']),
                        C_D_wpar == self.wing['k'] * C_f * self.wing["(\\frac{S}{S_{wet}})"]]

        return constraints

class Engine(Model):
    def setup(self):
        # Dimensional constants
        eta_prop    = Variable("\\eta_{prop}",0.8,'-',"propeller efficiency")
        P_shaft_ref = Variable("P_{shaft,ref}",149,"kW","reference MSL maximum shaft power")
        W_e_ref     = Variable("W_{e,ref}",153, "lbf","reference engine weight")

        # Free variables
        P_shaft_max = Variable("P_{shaft,max}","kW","MSL maximum shaft power")
        W_e         = Variable("W_e","N","engine weight")

        constraints = []
        constraints += [(W_e/W_e_ref)**1.92 >= 0.00441 * (P_shaft_max/P_shaft_ref)**0.759
                                + 1.44 * (P_shaft_max/P_shaft_ref)**2.90]
        return constraints

    def dynamic(self,state):
        return EngineP(self,state)

class EngineP(Model):
    def setup(self,engine,state):
        self.engine = engine
        # Dimensional constants
        BSFC        = Variable("BSFC", 400, "g/(kW*hr)", "brake specific fuel consumption")

        # Free variables
        P_shaft     = Variable("P_{shaft}","kW","shaft power")
        Thrust      = Variable("T","N","propeller thrust")

        constraints = []

        constraints += [P_shaft <= 0.2*self.engine['P_{shaft,max}']]

        return constraints


class Mission(Model):
    def setup(self,Nsegments):
        self.aircraft = SimPleAC()
        W_f_m   = Variable('W_{f_{m}}','N','Total mission fuel')
        t_m     = Variable('t_m','hr','Total mission time')

        with Vectorize(Nsegments):
            Wavg    = Variable('W_{avg}','N','Segment average weight')
            Wstart  = Variable('W_{start}', 'N', 'Weight at the beginning of flight segment')
            Wend    = Variable('W_{end}', 'N','Weight at the end of flight segment')
            h       = Variable('h','m','Flight altitude')
            havg    = Variable('h_{avg}','m','average segment flight altitude')
            dhdt    = Variable('\\frac{dh}{dt}','m/hr','Climb rate')
            W_f_s   = Variable('W_{f_s}','N', 'Segment fuel burn')
            t_s     = Variable('t_s','hr','Time spent in flight segment')
            R_s     = Variable('R_s','km','Range flown in segment')
            state   = Atmosphere()
            self.aircraftP = self.aircraft.dynamic(state)

        # Mission variables
        hcruise    = Variable('h_{cruise}', 5000, 'm', 'minimum cruise altitude')
        Range      = Variable("Range", 3000, "km", "aircraft range")
        W_p        = Variable("W_p", 6250, "N", "payload weight", pr=20.)
        V_min      = Variable("V_{min}", 25, "m/s", "takeoff speed", pr=20.)
        cost_index = Variable("C", 120,'1/hr','hourly cost index')

        constraints = []

        # Setting up the mission
        with SignomialsEnabled():
            constraints += [havg == state['h'],             # Linking states
                        h[1:Nsegments-1] >= hcruise,    # Adding minimum cruise altitude

                        # Weights at beginning and end of mission
                        Wstart[0] >= W_p + self.aircraft.wing['W_w'] + self.aircraft.engine['W_e'] + W_f_m,
                        Wend[Nsegments-1] >= W_p + self.aircraft.wing['W_w'] + self.aircraft.engine['W_e'],

                        # Lift, and linking segment start and end weights
                        Wavg <= 0.5 * state['\\rho'] * self.aircraft['S'] * self.aircraftP.wingP['C_L'] * self.aircraftP['V'] ** 2,
                        Wstart >= Wend + W_f_s, # Making sure fuel gets burnt!
                        Wstart[1:Nsegments] == Wend[:Nsegments-1],
                        Wavg == Wstart ** 0.5 * Wend ** 0.5,

                        # Altitude changes
                        h[0] == t_s[0]*dhdt[0], # Starting altitude
                        dhdt >= 1.*units('m/hr'),
                        havg[0] == 0.5 * h[0],
                        havg[1:Nsegments] == (h[1:Nsegments] * h[0:Nsegments - 1]) ** (0.5),
                        SignomialEquality(h[1:Nsegments],h[:Nsegments-1] + t_s[1:Nsegments]*dhdt[1:Nsegments]),

                        # Thrust and fuel burn
                        W_f_s >= self.aircraft['g'] * self.aircraftP.engineP['BSFC'] * self.aircraftP.engineP['P_{shaft}'] * t_s,
                        self.aircraftP.engineP['T'] * self.aircraftP['V'] >= self.aircraftP['D'] * self.aircraftP['V'] + Wavg * dhdt,

                        # Flight time
                        t_s == R_s/self.aircraftP['V'],

                        # Aggregating segment variables
                        self.aircraft['W_f'] >= W_f_m,
                        R_s == Range/Nsegments, # Dividing into equal range segments
                        W_f_m >= sum(W_f_s),
                        t_m >= sum(t_s)
                        ]

        # Maximum takeoff weight
        constraints += [self.aircraft['W'] >= W_p + self.aircraft.wing['W_w'] + self.aircraft['W_f'] + self.aircraft.engine['W_e']]

        # Stall constraint
        constraints += [self.aircraft['W'] <= 0.5 * state['\\rho'] *
                            self.aircraft['S'] * self.aircraft['C_{L,max}'] * V_min ** 2]

        # Wing weight model
        constraints += [self.aircraft.wing['W_{w_{strc}}']**2. >=
                        self.aircraft.wing['W_{w_{coeff1}}']**2. / self.aircraft.wing['\\tau']**2. *
                        (self.aircraft.wing['N_{ult}']**2. * self.aircraft.wing['A'] ** 3. *
                        ((W_p+self.aircraft.fuse['V_{f_{fuse}}']*self.aircraft['g']*self.aircraft['\\rho_f']) *
                         self.aircraft['W'] * self.aircraft.wing['S']))]

        return constraints, state, self.aircraft, self.aircraftP

if __name__ == "__main__":
    # Most basic way to execute the model 
    m = Mission(5)
    m.cost = m['W_f']*units('1/N') + m['C']*m['t_m']
    #m = Model(m.cost, Bounded(m))
    #m_relax = relaxed_constants(m,None,None)
    sol = m.localsolve(verbosity = 4)
    #post_process(sol)
    #print sol.table()
