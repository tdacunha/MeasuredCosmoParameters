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

import example_2_generate as example

# run posterior:
analyze_2d_example.run_example_2d(posterior_chain=example.posterior_chain,
                                  param_names=example.posterior_chain.getParamNames().list(),
                                  param_ranges=[[0.0, 0.6], [0.4, 1.5]],
                                  outroot=example.out_folder+'posterior_')

# run prior:
analyze_2d_example.run_example_2d(posterior_chain=example.prior_chain,
                                  param_names=example.posterior_chain.getParamNames().list(),
                                  outroot=example.out_folder+'prior_')


pass