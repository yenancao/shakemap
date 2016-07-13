#!/usr/bin/env python

import numpy as np

from openquake.hazardlib.gsim.base import GMPE
from openquake.hazardlib import const

from shakemap.grind.BeyerBommer2006 import ampIMCtoIMC, sigmaIMCtoIMC

class multigmpe(GMPE):
    """
    Implements a GMPE that is the combination of multiple GMPEs. 
    """
    
    DEFINED_FOR_TECTONIC_REGION_TYPE = None
    DEFINED_FOR_INTENSITY_MEASURE_TYPES = None
    DEFINED_FOR_INTENSITY_MEASURE_COMPONENT = None
    DEFINED_FOR_STANDARD_DEVIATION_TYPES = None
    REQUIRES_SITES_PARAMETERS = None
    REQUIRES_RUPTURE_PARAMETERS = None
    REQUIRES_DISTANCES = None
    
    def get_mean_and_stddevs(self, sites, rup, dists, imt, stddev_types):
        lnmu = np.zeros_like(sites.vs30)
        lnsd2 = np.zeros_like(sites.vs30)
        lmean = [None]*len(self.GMPEs)
        lsd = [None]*len(self.GMPEs)
        for i in range(len(self.GMPEs)):
            gmpe = self.GMPEs[i]
            # Need to select the appropriate z1pt0 value for different GMPEs.
            # Note that these are required site parameters, so even though
            # OQ has these equations built into the class, the arrays must
            # be provided in the sites context. It might be worth sending
            # a request to OQ to provide a subclass that that computes the
            # depth parameters when not provided (as is done for BSSA14 but
            # not the others). 
            if gmpe == 'AbrahamsonEtAl2014()':
                sites.z1pt0 = sites.z1pt0ask14
            if gmpe == 'BooreEtAl2014()' or gmpe == 'ChiouYoungs2014()':
                sites.z1pt0 = sites.z1pt0cy14
            lmean[i], lsd[i] = gmpe.get_mean_and_stddevs(
                sites, rup, dists, imt, stddev_types)
            
            # Convert component type.
            # Note: conversion is based on linear amps (not log)!!
            inc_in = self.IMCs[i]
            inc_out = self.DEFINED_FOR_INTENSITY_MEASURE_COMPONENT
            lmean[i] = np.log(ampIMCtoIMC(np.exp(lmean[i]), inc_in, inc_out, imt))
            lsd[i] = np.log(sigmaIMCtoIMC(np.exp(lsd[i]), inc_in, inc_out, imt))
            
            # Compute weighted mean and sd
            lnmu = lnmu + self.weights[i] * lmean[i]
            lnsd2 = lnsd2 + self.weights[i] * (lmean[i]**2 + lsd[i]**2)
        lnsd2 = lnsd2 - lnmu**2
        
        return lnmu, np.sqrt(lnsd2)
    
    @classmethod
    def fromList(cls, GMPEs, weights):
        """
        multigmpe constructor.
        :param GMPEs:
            List of OpenQuake GMPEs. 
        :param weights: 
            List of weights. 
        """
        self = cls()
        self.GMPEs = GMPEs
        self.weights = weights
        
        # Check that GMPEs all are for the same tectonic region,
        # otherwise raise exception. 
        tmp = set([i.DEFINED_FOR_TECTONIC_REGION_TYPE for i in GMPEs])
        if len(tmp) == 1:
            self.DEFINED_FOR_TECTONIC_REGION_TYPE = \
                GMPEs[0].DEFINED_FOR_TECTONIC_REGION_TYPE
        else:
            raise Exception('GMPEs are not all for the same tectonic region.')
        
        # Combine the intensity measure types. This is problematic:
        #   - Logically, we should only include the intersection of the sets
        #     of imts for the different GMPEs.
        #   - In practice, this is not feasible because most GMPEs in CEUS and
        #     subduction zones do not have PGV.
        #   - So instead we will use the union of the imts and then convert
        #     to get the missing imts later in get_mean_and_stddevs.
        imts = [g.DEFINED_FOR_INTENSITY_MEASURE_TYPES for g in GMPEs]
        self.DEFINED_FOR_INTENSITY_MEASURE_TYPES = set.union(*imts)
        
        # Store intensity measure types for conversion in get_mean_and_stddevs.
        self.IMCs = [g.DEFINED_FOR_INTENSITY_MEASURE_COMPONENT for g in GMPEs]
        
        # For ShakeMap, the target IMC is max
        self.DEFINED_FOR_INTENSITY_MEASURE_COMPONENT = \
            const.IMC.GREATER_OF_TWO_HORIZONTAL
        
        # For scenarios, we only care about total standard deviation,
        # but for real-time we need inter and intra. For now, lets
        # just take the intersection of the different GMPEs to make life
        # slightly easier.
        stdlist = [set(g.DEFINED_FOR_STANDARD_DEVIATION_TYPES) for g in GMPEs]
        self.DEFINED_FOR_STANDARD_DEVIATION_TYPES = set.intersection(*stdlist)
        
        # Need union of site parameters, but it is complicated by the
        # different depth parameter flavors.
        sitepars = [g.REQUIRES_SITES_PARAMETERS for g in GMPEs]
        self.REQUIRES_SITES_PARAMETERS = set.union(*sitepars)
        
        # Union of rupture parameters
        ruppars = [g.REQUIRES_RUPTURE_PARAMETERS for g in GMPEs]
        self.REQUIRES_RUPTURE_PARAMETERS = set.union(*ruppars)
        
        # Union of distance parameters
        distpars = [g.REQUIRES_DISTANCES for g in GMPEs]
        self.REQUIRES_DISTANCES = set.union(*distpars)
        
        return self
    
