from gpkit import Model, Variable, SignomialsEnabled, VarKey, units
from gpkit.constraints.bounded import Bounded
import numpy as np
import matplotlib.pyplot as plt

class SimPleAC(Model):
    def setup(self):
        self.engine = Engine()
        self.components = [self.engine]
        # Env. constants
        g          = Variable("g", 9.81, "m/s^2", "gravitational acceleration")
        mu         = Variable("\\mu", 1.775e-5, "kg/m/s", "viscosity of air", pr=4.)
        rho        = Variable("\\rho", 1.23, "kg/m^3", "density of air", pr=5.)
        rho_f      = Variable("\\rho_f", 817, "kg/m^3", "density of fuel")
        
        # Non-dimensional constants
        C_Lmax     = Variable("C_{L,max}", 1.6, "-", "max CL with flaps down", pr=5.)
        e          = Variable("e", 0.92, "-", "Oswald efficiency factor", pr=3.)
        k          = Variable("k", 1.17, "-", "form factor", pr=10.)
        N_ult      = Variable("N_{ult}", 3.3, "-", "ultimate load factor", pr=15.)
        S_wetratio = Variable("(\\frac{S}{S_{wet}})", 2.075, "-", "wetted area ratio", pr=3.)
        tau        = Variable("\\tau", 0.12, "-", "airfoil thickness to chord ratio", pr=10.)
        W_W_coeff1 = Variable("W_{W_{coeff1}}", 2e-5, "1/m",
                              "wing weight coefficent 1", pr= 30.) #orig  12e-5
        W_W_coeff2 = Variable("W_{W_{coeff2}}", 60., "Pa",
                              "wing weight coefficent 2", pr=10.)
        p_labor    = Variable('p_{labor}',1.,'1/min','cost of labor', pr = 20.)

        # Dimensional constants
        Range     = Variable("Range",3000, "km", "aircraft range")
        V_min     = Variable("V_{min}", 25, "m/s", "takeoff speed", pr=20.)
        W_p       = Variable("W_p", 6250, "N", "payload weight", pr=20.)
        
        # Free Variables
        LoD       = Variable('L/D','-','lift-to-drag ratio')
        D         = Variable("D", "N", "total drag force")
        V         = Variable("V", "m/s", "cruising speed")
        W         = Variable("W", "N", "total aircraft weight")
        Re        = Variable("Re", "-", "Reynolds number")
        CDA0      = Variable("(CDA0)", "m^2", "fuselage drag area") #0.035 originally
        C_D       = Variable("C_D", "-", "drag coefficient")
        C_L       = Variable("C_L", "-", "wing lift coefficient")
        C_f       = Variable("C_f", "-", "skin friction coefficient")
        W_f       = Variable("W_f", "N", "fuel weight")
        V_f       = Variable("V_f", "m^3", "fuel volume")
        V_f_avail = Variable("V_{f_{avail}}","m^3","fuel volume available")
        T_flight  = Variable("T_{flight}", "hr", "flight time")
        
        # Free variables (fixed for performance eval.)
        A         = Variable("A", "-", "aspect ratio",fix = True)
        S         = Variable("S", "m^2", "total wing area", fix = True)
        W_w       = Variable("W_w", "N", "wing weight")#, fix = True)
        W_w_strc  = Variable('W_{w_{strc}}','N','wing structural weight', fix = True)
        W_w_surf  = Variable('W_{w_{surf}}','N','wing skin weight', fix = True)
        V_f_wing  = Variable("V_{f_{wing}}",'m^3','fuel volume in the wing', fix = True)
        V_f_fuse  = Variable('V_{f_{fuse}}','m^3','fuel volume in the fuselage', fix = True)
        constraints = []
  
        # Weight and lift model
        constraints += [W >= W_p + W_w + W_f + self.engine['W_e'],
                    W_p + W_w + 0.5 * W_f + self.engine['W_e'] <= 0.5 * rho * S * C_L * V ** 2,
                    W <= 0.5 * rho * S * C_Lmax * V_min ** 2,
                    T_flight >= Range / V,
                    LoD == C_L/C_D]

        # Thrust and drag model
        C_D_fuse = CDA0 / S
        C_D_wpar = k * C_f * S_wetratio
        C_D_ind  = C_L ** 2 / (np.pi * A * e)
        constraints += [W_f >= g * self.engine['BSFC'] * self.engine['P_{shaft}'] * T_flight,
                    self.engine['T'] >= D,
                    self.engine['T']*V <= self.engine['\\eta_{prop}']*self.engine['P_{shaft}'],
                    D >= 0.5 * rho * S * C_D * V ** 2,
                    C_D >= C_D_fuse + C_D_wpar + C_D_ind,
                    V_f_fuse <= 10*units('m')*CDA0,
                    Re <= (rho / mu) * V * (S / A) ** 0.5,
                    C_f >= 0.074 / Re ** 0.2]

        # Fuel volume model 
        with SignomialsEnabled():
            constraints +=[V_f == W_f / g / rho_f,
                    V_f_wing**2 <= 0.0009*S**3/A*tau**2, # linear with b and tau, quadratic with chord
                    V_f_avail <= V_f_wing + V_f_fuse, #[SP]
                    V_f_avail >= V_f
                    ]

        # Wing weight model
        constraints += [W_w_surf >= W_W_coeff2 * S,
                    W_w_strc**2. >= W_W_coeff1**2. / tau**2. * (N_ult**2. * A ** 3. * ((W_p+V_f_fuse*g*rho_f) * W * S)),
                    W_w >= W_w_surf + W_w_strc]

        return constraints, self.components


class Engine(Model):
    def setup(self):
        # Dimensional constants
        eta_prop    = Variable("\\eta_{prop}",0.8,'-',"propeller efficiency")
        P_shaft_ref = Variable("P_{shaft_{ref}}",149,"kW","reference MSL maximum shaft power")
        BSFC        = Variable("BSFC", 400, "g/(kW*hr)", "thrust specific fuel consumption")
        W_e_ref     = Variable("W_{e_{ref}}",681,"N","reference engine weight")

        # Free variables
        P_shaft     = Variable("P_{shaft}","kW","shaft power")
        P_shaft_max = Variable("P_{shaft_{max}}","kW","MSL maximum shaft power")
        Thrust      = Variable("T","N","propeller thrust")
        W_e         = Variable("W_e","N","engine weight")

        constraints = [P_shaft <= 0.2*P_shaft_max,
                       (W_e/W_e_ref)**1.92 >= 0.00441 * (P_shaft_max/P_shaft_ref)**0.759
                                + 1.44 * (P_shaft_max/P_shaft_ref)**2.90
                    ]
        return constraints        

if __name__ == "__main__":
    # Most basic way to execute the model 
    m = SimPleAC()
    m.cost = m['W_f'] 
    sol = m.localsolve(verbosity = 1)
    print sol.table()
