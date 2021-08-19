# -*- coding: utf-8 -*-

"""
Generate data for example: non-Gaussian resembling DES.
"""

###############################################################################
# initial imports:
import os
import numpy as np

import sys
here = './'
temp_path = os.path.realpath(os.path.join(os.getcwd(), here+'tensiometer'))
sys.path.insert(0, temp_path)
import getdist
from getdist import plots, MCSamples
from getdist.gaussian_mixtures import GaussianND
import tensiometer.gaussian_tension as gaussian_tension

import synthetic_probability
from tensorflow.keras.callbacks import ReduceLROnPlateau
callbacks = [ReduceLROnPlateau()]

###############################################################################
# initial settings:

# output folder:
out_folder = './results/example_2/'
if not os.path.exists(out_folder):
    os.mkdir(out_folder)

# cache for training:
flow_cache = out_folder+'flow_cache/'
if not os.path.exists(flow_cache):
    os.mkdir(flow_cache)

# number of samples:
n_samples = 100000

###############################################################################
# define the pdf from the DES samples:

# load the chains (remove no burn in since the example chains have already been cleaned):
chains_dir = here+'/tensiometer/test_chains/'
# the DES chain:
settings = {'ignore_rows': 0, 'smooth_scale_1D': 0.3, 'smooth_scale_2D': 0.3}
chain = getdist.mcsamples.loadMCSamples(file_root=chains_dir+'DES', no_cache=True, settings=settings)
# the prior chain:
prior_chain = getdist.mcsamples.loadMCSamples(file_root=chains_dir+'prior', no_cache=True, settings=settings)

# select parameters:
param_names = ['omegam', 'sigma8']

# get the posterior chain:

# add log of the parameters:
for ch in [chain]:
    for name in param_names:
        ch.addDerived(np.log(ch.samples[:, ch.index[name]]), name='log_'+name, label='\\log'+ch.getParamNames().parWithName(name).label)
    # update after adding all parameters:
    ch.updateBaseStatistics()

# now we generate the Gaussian approximation:
temp_param_names = ['log_'+name for name in param_names]

# create the Gaussian:
gauss = gaussian_tension.gaussian_approximation(chain, param_names=temp_param_names)
posterior_chain = gauss.MCSamples(size=n_samples)

# exponentiate:
for ch in [posterior_chain]:
    p = ch.getParams()
    # the original parameters:
    for ind, name in enumerate(temp_param_names):
        ch.addDerived(np.exp(ch.samples[:, ch.index[name]]), name=str(name).replace('log_', ''), label=str(ch.getParamNames().parWithName(name).label).replace('\\log', ''))
    # label=ch.getParamNames().parWithName(name).label.replace('\\log ','')
    ch.updateBaseStatistics()

# define the new samples:
posterior_chain = MCSamples(samples=posterior_chain.samples[:, [posterior_chain.index[name] for name in param_names]],
                            names=['theta_'+str(i+1) for i in range(len(param_names))],
                            labels=['\\theta_{'+str(i+1)+'}' for i in range(len(param_names))],
                            label='posterior')

# get the prior chain:
_mins = np.amin(prior_chain.samples[:, [prior_chain.index[name] for name in param_names]], axis=0)
_maxs = np.amax(prior_chain.samples[:, [prior_chain.index[name] for name in param_names]], axis=0)

_mins = [0.0, 0.0]
_maxs = [0.7, 1.7]

prior_samples = []
for _min, _max in zip(_mins, _maxs):
    prior_samples.append(np.random.uniform(_min, _max, size=n_samples))
prior_samples = np.array(prior_samples).T

prior_chain = MCSamples(samples=prior_samples,
                        names=['theta_'+str(i+1) for i in range(len(param_names))],
                        labels=['\\theta_{'+str(i+1)+'}' for i in range(len(param_names))],
                        label='prior')

###############################################################################
# define the flows:

# if cache exists load training:
if os.path.isfile(flow_cache+'posterior'+'_permutations.pickle'):
    # load trained model:
    temp_MAF = synthetic_probability.SimpleMAF.load(len(posterior_chain.getParamNames().list()), flow_cache+'posterior')
    # initialize flow:
    posterior_flow = synthetic_probability.DiffFlowCallback(posterior_chain, Z2Y_bijector=temp_MAF.bijector, param_names=posterior_chain.getParamNames().list(), feedback=0, learning_rate=0.01)
else:
    # initialize flow:
    posterior_flow = synthetic_probability.DiffFlowCallback(posterior_chain, param_names=posterior_chain.getParamNames().list(), feedback=1, learning_rate=0.01)
    # train:
    posterior_flow.train(batch_size=8192, epochs=40, steps_per_epoch=128, callbacks=callbacks)
    # save trained model:
    posterior_flow.MAF.save(flow_cache+'posterior')

prior_bij = synthetic_probability.prior_bijector_helper([{'mean':.25, 'scale':.3}, {'mean':.85, 'scale':.3}])
prior_flow = synthetic_probability.DiffFlowCallback(prior_chain, Z2Y_bijector=prior_bij, Y2X_is_identity=True)
#
# # if cache exists load training:
# if os.path.isfile(flow_cache+'prior'+'_permutations.pickle'):
#     # load trained model:
#     #temp_MAF = synthetic_probability.SimpleMAF.load(len(prior_chain.getParamNames().list()), flow_cache+'prior')
#     # initialize flow:
#     prior_bij = synthetic_probability.prior_bijector_helper([{'mean':.25, 'scale':.2}, {'mean':.85, 'scale':.2}])
#     prior_flow = synthetic_probability.DiffFlowCallback(prior_chain, Z2Y_bijector=prior_bij, Y2X_is_identity=True)
#     #prior_flow = synthetic_probability.DiffFlowCallback(prior_chain, Z2Y_bijector=temp_MAF.bijector, param_names=prior_chain.getParamNames().list(), feedback=0, learning_rate=0.01)
# else:
#     # initialize flow:
#     prior_bij = synthetic_probability.prior_bijector_helper([{'mean':.25, 'scale':.2}, {'mean':.85, 'scale':.2}])
#     prior_flow = synthetic_probability.DiffFlowCallback(prior_chain, Z2Y_bijector=prior_bij, Y2X_is_identity=True)
#     #prior_flow = synthetic_probability.DiffFlowCallback(prior_chain, param_names=prior_chain.getParamNames().list(), feedback=1, learning_rate=0.01)
#     # train:
#     #prior_flow.train(batch_size=8192, epochs=40, steps_per_epoch=128, callbacks=callbacks)
#     # save trained model:
#     #prior_flow.MAF.save(flow_cache+'prior')


###############################################################################
# test plot if called directly:
if __name__ == '__main__':

    # feedback:
    print('* plotting generated sample')

    # plot distribution:
    g = plots.get_subplot_plotter()
    g.triangle_plot([prior_chain, posterior_chain], filled=True)
    g.export(out_folder+'0_prior_posterior.pdf')

    g = plots.get_subplot_plotter()
    g.triangle_plot([posterior_chain], filled=True)
    g.export(out_folder+'0_posterior.pdf')

    # plot learned posterior distribution:
    X_sample = np.array(posterior_flow.sample(n_samples))
    posterior_flow_chain = MCSamples(samples=X_sample,
                                     loglikes=-posterior_flow.log_probability(X_sample).numpy(),
                                     names=posterior_flow.param_names,
                                     label='Learned distribution')
    g = plots.get_subplot_plotter()
    g.triangle_plot([posterior_chain, posterior_flow_chain], filled=True)
    g.export(out_folder+'0_learned_posterior_distribution.pdf')

    # plot learned prior distribution:
    X_sample = np.array(prior_flow.sample(n_samples))
    prior_flow_chain = MCSamples(samples=X_sample,
                                 loglikes=-prior_flow.log_probability(X_sample).numpy(),
                                 names=prior_flow.param_names,
                                 label='Learned distribution')
    g = plots.get_subplot_plotter()
    g.triangle_plot([prior_chain, prior_flow_chain], filled=True)
    g.export(out_folder+'0_learned_prior_distribution.pdf')


# Testing to see if local metric problem starts here:
param_ranges = [[0,.6],[.6,1.3]]
coarse_P1 = np.linspace(param_ranges[0][0], param_ranges[0][1], 20)
coarse_P2 = np.linspace(param_ranges[1][0], param_ranges[1][1], 20)
coarse_x, coarse_y = coarse_P1, coarse_P2
coarse_X, coarse_Y = np.meshgrid(coarse_x, coarse_y)

coords = np.array([coarse_X, coarse_Y], dtype=np.float32).reshape(2, -1).T
#print(coords)
local_metrics = posterior_flow.metric(coords)
print(local_metrics)
