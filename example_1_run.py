# -*- coding: utf-8 -*-

"""
Run analysis on all examples
"""

###############################################################################
# initial imports:
import os
import numpy as np
import copy
import pickle
import sys
here = './'
temp_path = os.path.realpath(os.path.join(os.getcwd(), here+'tensiometer'))
sys.path.insert(0, temp_path)
import getdist
from getdist import plots, MCSamples
from getdist.gaussian_mixtures import GaussianND
import tensiometer.gaussian_tension as gaussian_tension
from scipy import optimize

import analyze_2d_example

###############################################################################
# run example:

import example_1_generate as example

# run posterior:
analyze_2d_example.run_example_2d(chain=example.posterior_chain,
                                  flow=example.posterior_flow,
                                  param_names=example.posterior_chain.getParamNames().list(),
                                  param_ranges=[[0.0, 0.5], [0.3, 1.5]],
                                  outroot=example.out_folder+'posterior_')

# run prior:
analyze_2d_example.run_example_2d(chain=example.prior_chain,
                                  flow=example.prior_flow,
                                  param_names=example.prior_chain.getParamNames().list(),
                                  param_ranges=[[-6, 12], [-1, 3]],
                                  outroot=example.out_folder+'prior_')

pass
