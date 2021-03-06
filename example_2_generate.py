# -*- coding: utf-8 -*-

"""
Generate data for example: non-Gaussian resembling DES.
"""

###############################################################################
# initial imports:
import os
import numpy as np
import pickle

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
n_samples = 1000000

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

_mins = np.array([0.0, 0.0])
_maxs = np.array([0.7, 1.7])

prior_samples = []
param_ranges = {}
for _min, _max, name in zip(_mins, _maxs, ['theta_'+str(i+1) for i in range(len(param_names))]):
    prior_samples.append(np.random.uniform(_min, _max, size=n_samples))
    param_ranges[name] = [_min, _max]
prior_samples = np.array(prior_samples).T

prior_chain = MCSamples(samples=prior_samples,
                        names=['theta_'+str(i+1) for i in range(len(param_names))],
                        labels=['\\theta_{'+str(i+1)+'}' for i in range(len(param_names))],
                        label='prior')

###############################################################################
# define the flows:

# exact prior:
temp = []
for lower, upper in zip(_mins, _maxs):
    temp.append({'lower': lower.astype(np.float32), 'upper': upper.astype(np.float32)})
prior_bij = synthetic_probability.prior_bijector_helper(temp)
prior_flow = synthetic_probability.DiffFlowCallback(prior_chain,
                                                    prior_bijector=prior_bij, apply_pregauss=False, trainable_bijector=None,
                                                    param_ranges=param_ranges, param_names=prior_chain.getParamNames().list(), feedback=1)

# posterior:
num_params = len(param_names)
n_maf = 4*num_params
hidden_units = [num_params*4]*3
batch_size = 2*8192
epochs = 80
steps_per_epoch = 128

# if cache exists load training:
if os.path.isfile(flow_cache+'posterior'+'_permutations.pickle'):
    # load trained model:
    temp_MAF = synthetic_probability.SimpleMAF.load(len(posterior_chain.getParamNames().list()), flow_cache+'posterior', n_maf=n_maf, hidden_units=hidden_units)
    # initialize flow:
    posterior_flow = synthetic_probability.DiffFlowCallback(posterior_chain,
                                                            prior_bijector=prior_bij, trainable_bijector=temp_MAF.bijector,
                                                            param_ranges=param_ranges, param_names=posterior_chain.getParamNames().list(),
                                                            feedback=0, learning_rate=0.01)
else:
    # initialize flow:
    posterior_flow = synthetic_probability.DiffFlowCallback(posterior_chain,
                                                            prior_bijector=prior_bij,
                                                            param_ranges=param_ranges, param_names=posterior_chain.getParamNames().list(),
                                                            feedback=1, learning_rate=0.01, n_maf=n_maf, hidden_units=hidden_units)
    # train:
    posterior_flow.global_train(batch_size=batch_size, epochs=epochs, steps_per_epoch=steps_per_epoch, callbacks=callbacks)
    # save trained model:
    posterior_flow.MAF.save(flow_cache+'posterior')

# find MAP or load if it exists:
if os.path.isfile(flow_cache+'/posterior_MAP.pickle'):
    temp = pickle.load(open(flow_cache+'/posterior_MAP.pickle', 'rb'))
    posterior_flow.MAP_coord = temp['MAP_coord']
    posterior_flow.MAP_logP = temp['MAP_logP']
else:
    # find map:
    res = posterior_flow.MAP_finder(disp=True)
    print(res)
    # store:
    temp = {
            'MAP_coord': posterior_flow.MAP_coord,
            'MAP_logP': posterior_flow.MAP_logP,
            }
    # save out:
    pickle.dump(temp, open(flow_cache+'/posterior_MAP.pickle', 'wb'))

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
    g = plots.get_subplot_plotter()
    g.triangle_plot([posterior_chain, posterior_flow.MCSamples(n_samples)], filled=True, markers=posterior_flow.MAP_coord)
    g.export(out_folder+'0_learned_posterior_distribution.pdf')

    # plot learned prior distribution:
    g = plots.get_subplot_plotter()
    g.triangle_plot([prior_chain, prior_flow.MCSamples(n_samples)], filled=True)
    g.export(out_folder+'0_learned_prior_distribution.pdf')
