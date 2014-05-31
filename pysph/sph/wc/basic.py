"""Basic WCSPH equations.
"""

from pysph.sph.equation import Equation
from textwrap import dedent

class TaitEOS(Equation):
    def __init__(self, dest, sources=None,
                 rho0=1000.0, c0=1.0, gamma=7.0, p0=0.0):
        self.rho0 = rho0
        self.rho01 = 1.0/rho0
        self.c0 = c0
        self.gamma = gamma
        self.gamma1 = 0.5*(gamma - 1.0)
        self.B = rho0*c0*c0/gamma
        self.p0 = p0
        super(TaitEOS, self).__init__(dest, sources)

    def loop(self, d_idx, d_rho, d_p, d_cs):
        ratio = d_rho[d_idx] * self.rho01
        tmp = pow(ratio, self.gamma)

        d_p[d_idx] = self.p0 + self.B * (tmp - 1.0)
        d_cs[d_idx] = self.c0 * pow( ratio, self.gamma1 )

class TaitEOSHGCorrection(Equation):
    """Tait Equation of state with Hughes and Graham Correction
    
    The correction is described in "Comparison of incompressible and
    weakly-compressible SPH models for free-surface water flows",
    Journal of Hydraullic Research, 2010, 48

    The correction is to be applied on boundary particles and imposes
    a minimum value of the density (rho0) which is set upon
    instantiation. This correction avoids particle sticking behaviour
    at walls.

    """
    def __init__(self, dest, sources=None,
                 rho0=1000.0, c0=1.0, gamma=7.0):
        self.rho0 = rho0
        self.rho01 = 1.0/rho0
        self.c0 = c0
        self.gamma = gamma
        self.gamma1 = 0.5*(gamma - 1.0)
        self.B = rho0*c0*c0/gamma
        super(TaitEOSHGCorrection, self).__init__(dest, sources)

    def loop(self, d_idx, d_rho, d_p, d_cs):
        if d_rho[d_idx] < self.rho0:
            d_rho[d_idx] = self.rho0

        ratio = d_rho[d_idx] * self.rho01
        tmp = pow(ratio, self.gamma)
                
        d_p[d_idx] = self.B * (tmp - 1.0)
        d_cs[d_idx] = self.c0 * pow( ratio, self.gamma1 )

class MomentumEquation(Equation):
    def __init__(self, dest, sources=None,
                 alpha=1.0, beta=1.0, eta=0.1, gx=0.0, gy=0.0, gz=0.0,
                 c0=1.0, tensile_correction=False):

        self.alpha = alpha
        self.beta = beta
        self.eta = eta
        self.gx = gx
        self.gy = gy
        self.gz = gz
        self.dt_fac = 0.0
        self.c0 = c0

        self.tensile_correction = tensile_correction
        
        super(MomentumEquation, self).__init__(dest, sources)

    def initialize(self, d_idx, d_au, d_av, d_aw):
        d_au[d_idx] = 0.0
        d_av[d_idx] = 0.0
        d_aw[d_idx] = 0.0

    def cython_code(self):
        code = dedent("""
        from libc.math cimport pow, fabs
        """)

        return dict(helper=code)

    def loop(self, d_idx, s_idx, d_rho, d_cs,
             d_p, d_au, d_av, d_aw, s_m,
             s_rho, s_cs, s_p, VIJ=[0.0, 0.0, 0.0],
             XIJ=[0.0, 0.0, 0.0], HIJ=1.0, R2IJ=1.0, RHOIJ1=1.0,
             DWIJ=[1.0, 1.0, 1.0], DT_ADAPT=[0.0, 0.0, 0.0],
             WIJ=0.0, WDP=0.0):

        rhoi21 = 1.0/(d_rho[d_idx]*d_rho[d_idx])
        rhoj21 = 1.0/(s_rho[s_idx]*s_rho[s_idx])
        
        pi = d_p[d_idx]
        pj = s_p[s_idx]

        vijdotxij = VIJ[0]*XIJ[0] + VIJ[1]*XIJ[1] + VIJ[2]*XIJ[2]

        piij = 0.0
        if vijdotxij < 0:
            cij = 0.5 * (d_cs[d_idx] + s_cs[s_idx])

            muij = (HIJ * vijdotxij)/(R2IJ + self.eta*self.eta*HIJ*HIJ)

            piij = -self.alpha*cij*muij + self.beta*muij*muij
            piij = piij*RHOIJ1

        # compute the CFL time step factor
        _dt_fac = 0.0
        if R2IJ > 1e-12:
            _dt_fac = abs( HIJ * vijdotxij/R2IJ ) + self.c0
            DT_ADAPT[0] = max(_dt_fac, DT_ADAPT[0])

        tmpi = d_p[d_idx]*rhoi21
        tmpj = s_p[s_idx]*rhoj21

        fij = WIJ/WDP
        Ri = 0.0; Rj = 0.0

        #tmp = d_p[d_idx] * rhoi21 + s_p[s_idx] * rhoj21
        #tmp = tmpi + tmpj

        # tensile instability correction
        if self.tensile_correction:
            fij = fij*fij
            fij = fij*fij

            if d_p[d_idx] > 0 : 
                Ri = 0.01 * tmpi
            else:
                Ri = 0.2*abs( tmpi )

            if s_p[s_idx] > 0:
                Rj = 0.01 * tmpj
            else:
                Rj = 0.2 * abs( tmpj )

        # gradient and correction terms
        tmp = (tmpi + tmpj) + (Ri + Rj)*fij

        d_au[d_idx] += -s_m[s_idx] * (tmp + piij) * DWIJ[0]
        d_av[d_idx] += -s_m[s_idx] * (tmp + piij) * DWIJ[1]
        d_aw[d_idx] += -s_m[s_idx] * (tmp + piij) * DWIJ[2]

    def post_loop(self, d_idx, d_au, d_av, d_aw):
        d_au[d_idx] +=  self.gx
        d_av[d_idx] +=  self.gy
        d_aw[d_idx] +=  self.gz
