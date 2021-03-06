"""
General code to analyze examples

For testing purposes:

import example_2_generate as example
import example_5_generate as example
import example_1_generate as example

import example_3_generate as example


chain = example.posterior_chain
prior_chain = example.prior_chain
flow = example.posterior_flow
prior_flow = example.prior_flow
param_names = example.posterior_chain.getParamNames().list()
prior_param_names=example.prior_chain.getParamNames().list()
outroot = example.out_folder+'KL_'
train_params = {}
param_ranges = None #[[-1.5, 1.5], [-1.5, 1.5]] #None # [[0.0, 0.6], [0.4, 1.5]]

"""

###############################################################################
# initial imports:
import os
import numpy as np

import sys
here = './'
temp_path = os.path.realpath(os.path.join(os.getcwd(), here+'tensiometer'))
sys.path.insert(0, temp_path)
import synthetic_probability
from tensorflow.keras.callbacks import ReduceLROnPlateau
callbacks = [ReduceLROnPlateau()]
from getdist import plots, MCSamples

from scipy import optimize
from scipy.integrate import simps
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import scipy.stats
import matplotlib.gridspec as gridspec

# import the tensiometer tools that we need:
from tensiometer import utilities
from tensiometer import gaussian_tension
from tensiometer import mcmc_tension

# tensorflow imports:
import tensorflow as tf
import tensorflow_probability as tfp

###############################################################################
# general utility functions:


# helper function to get levels:
def get_levels(P, x, y, conf=[0.95, 0.68]):
    """
    Get levels from a 2D grid
    """
    def _helper(alpha):
        _P = P.copy()
        _P[_P < alpha] = 0.
        return simps(simps(_P, y), x)
    levs = []
    for c in conf:
        try:
            res = optimize.brentq(lambda x: _helper(x)-c, np.amin(P), np.amax(P))
            levs.append(res)
        except:
            print('Cannot generate proper levels')
            levs = len(conf)
            break

    return levs


def run_KL_example_2d(chain, prior_chain, flow, prior_flow, param_names, outroot, param_ranges=None, use_MAP=True):
    """
    Run full KL analysis of 2d example case, as in flow playground
    """

    # plotting preferences:
    figsize = (8, 8)
    fontsize = 15

    # parameter ranges for plotting from the prior:
    if param_ranges is None:
        param_ranges = np.array([np.amin(chain.samples, axis=0), np.amax(chain.samples, axis=0)]).T
        param_ranges = param_ranges[[chain.index[name] for name in param_names], :]

    # parameter labels:
    param_labels = [name.label for name in chain.getParamNames().parsWithNames(param_names)]
    param_labels_latex = ['$'+name+'$' for name in param_labels]

    # parameter grids:
    P1 = np.linspace(param_ranges[0][0], param_ranges[0][1], 200)
    P2 = np.linspace(param_ranges[1][0], param_ranges[1][1], 200)
    x, y = P1, P2
    X, Y = np.meshgrid(x, y)

    # coarse parameter grid:
    coarse_P1 = np.linspace(param_ranges[0][0], param_ranges[0][1], 20)
    coarse_P2 = np.linspace(param_ranges[1][0], param_ranges[1][1], 20)
    coarse_x, coarse_y = coarse_P1, coarse_P2
    coarse_X, coarse_Y = np.meshgrid(coarse_x, coarse_y)

    # obtain posterior on grid from samples:
    density = chain.get2DDensity(param_names[0], param_names[1], normalized=True)
    _X, _Y = np.meshgrid(density.x, density.y)
    density.P = density.P / simps(simps(density.P, density.y), density.x)

    # levels for contour plots:
    levels_5 = [utilities.from_sigma_to_confidence(i) for i in range(5, 0, -1)]
    levels_3 = [utilities.from_sigma_to_confidence(i) for i in range(3, 0, -1)]

    log_P = flow.log_probability(np.array([X, Y], dtype=np.float32).T)
    log_P = np.array(log_P).T
    P = np.exp(log_P)
    P = P / simps(simps(P, y), x)

    log_Pi = prior_flow.log_probability(np.array([X, Y], dtype=np.float32).T)
    log_Pi = np.array(log_Pi).T
    Pi = np.exp(log_Pi)
    Pi = Pi / simps(simps(Pi, y), x)

    log_L = log_P - log_Pi
    Like = np.exp(log_L)
    Like = Like / simps(simps(Like, y), x)

    ###############################################################################

    # find the MAPS:
    #result = flow.MAP_finder(disp=True)
    #maximum_posterior = result.x
    maximum_posterior = flow.MAP_coord
    # mean:
    mean = chain.getMeans([chain.index[name] for name in param_names])

    if use_MAP:
        reference_point = maximum_posterior
    else:
        reference_point = mean

    # from samples:
    cov_samples = chain.cov(pars=param_names)
    prior_cov_samples = prior_chain.cov(pars=param_names)

    fisher_samples = np.linalg.inv(cov_samples)
    prior_fisher_samples = np.linalg.inv(prior_cov_samples)

    # metrics from flow around mean:
    covariance_metric = flow.inverse_metric(np.array([reference_point]).astype(np.float32))[0]
    fisher_metric = flow.metric(np.array([reference_point]).astype(np.float32))[0]

    prior_covariance_metric = prior_flow.inverse_metric(np.array([reference_point]).astype(np.float32))[0]
    prior_fisher_metric = prior_flow.metric(np.array([reference_point]).astype(np.float32))[0]

    ###############################################################################
    # TF KL decomposition:

    @tf.function
    def tf_KL_decomposition(matrix_a, matrix_b):
        """
        """
        # compute the eigenvalues of b, lambda_b:
        _lambda_b, _phi_b = tf.linalg.eigh(matrix_b)
        _sqrt_lambda_b = tf.linalg.diag(1./tf.math.sqrt(_lambda_b))
        _phib_prime = tf.matmul(_phi_b, _sqrt_lambda_b)
        #
        trailing_axes = [-1, -2]
        leading = tf.range(tf.rank(_phib_prime) - len(trailing_axes))
        trailing = trailing_axes + tf.rank(_phib_prime)
        new_order = tf.concat([leading, trailing], axis=0)
        _phib_prime_T = tf.transpose(_phib_prime, new_order)
        #
        _a_prime = tf.matmul(tf.matmul(_phib_prime_T, matrix_a), _phib_prime)
        _lambda, _phi_a = tf.linalg.eigh(_a_prime)
        _phi = tf.matmul(tf.matmul(_phi_b, _sqrt_lambda_b), _phi_a)
        return _lambda, _phi

    ###############################################################################
    # Plot of KL eigenvectors at mean (covariance, fisher, samples)
    ###############################################################################

    alpha = np.linspace(-1, 1, 1000)
    plt.figure(figsize=figsize)

    # plot KL of flow local fisher metric
    eig, eigv = tf_KL_decomposition(fisher_metric, prior_fisher_metric)
    eig, eigv = eig.numpy(), eigv.numpy()

    mode = 0
    norm0 = np.linalg.norm(eigv[:, 0])
    plt.plot(mean[0]+alpha*eigv[0, mode]/norm0, mean[1]+alpha*eigv[1, mode]/norm0, lw=1., color='green', ls='-.', label='KL flow fisher', alpha=.5)
    mode = 1
    norm1 = np.linalg.norm(eigv[:, 1])
    plt.plot(mean[0]+alpha*eigv[0, mode]/norm1, mean[1]+alpha*eigv[1, mode]/norm1, lw=1., color='green', ls='-.', alpha=.5)

    # plot KL of global fisher:
    eig, eigv = tf_KL_decomposition(fisher_samples, prior_fisher_samples)
    eig, eigv = eig.numpy(), eigv.numpy()

    mode = 0
    norm0 = np.linalg.norm(eigv[:, 0])
    plt.plot(mean[0]+alpha*eigv[0, mode]/norm0, mean[1]+alpha*eigv[1, mode]/norm0, lw=1., color='red', ls='--', label='KL samples fisher', alpha=.5)
    mode = 1
    norm1 = np.linalg.norm(eigv[:, 1])
    plt.plot(mean[0]+alpha*eigv[0, mode]/norm1, mean[1]+alpha*eigv[1, mode]/norm1, lw=1., color='red', ls='--', alpha=.5)

    # plot contours
    plt.contour(X, Y, P, get_levels(P, x, y, levels_5), linewidths=1., linestyles='-', colors=['k' for i in levels_5])
    plt.scatter(mean[0], mean[1], color='k')

    plt.legend()
    plt.xlim([np.amin(P1), np.amax(P1)])
    plt.ylim([np.amin(P2), np.amax(P2)])
    plt.legend()
    plt.xlabel(param_labels_latex[0], fontsize=fontsize)
    plt.ylabel(param_labels_latex[1], fontsize=fontsize)
    plt.tight_layout()
    plt.savefig(outroot+'1_comparison_of_cov_fisher_samples_at_mean.pdf')
    plt.close('all')

    ##########################################################################
    # Plot of local KL eigenvectors
    ##########################################################################

    r = np.linspace(-1, 1, 1000)

    coords = np.array([coarse_X, coarse_Y], dtype=np.float32).reshape(2, -1).T

    # compute the metric at all coordinates
    local_metrics = flow.metric(coords)
    prior_local_metrics = prior_flow.metric(coords)

    # compute KL decomposition:
    KL_eig, KL_eigv = tf_KL_decomposition(local_metrics, prior_local_metrics)
    idx = np.argsort(KL_eig, axis=1)[0]
    KL_eig = KL_eig.numpy()[:, idx]
    KL_eigv = KL_eigv.numpy()[:, :, idx]

    # plot KL eigenvectors
    mode = 0
    plt.figure(figsize=figsize)
    plt.quiver(coords[:, 0], coords[:, 1], KL_eigv[:, 0, mode], KL_eigv[:, 1, mode], color='red', angles='xy', label='First mode')
    mode = 1
    plt.quiver(coords[:, 0], coords[:, 1], KL_eigv[:, 0, mode], KL_eigv[:, 1, mode], color='cadetblue', angles='xy', label='Second mode')

    # plot contours
    plt.contour(X, Y, P, get_levels(P, x, y, levels_5), linewidths=1., linestyles='-', colors=['k' for i in levels_5])
    plt.scatter(maximum_posterior[0], maximum_posterior[1], color='k')

    # compute and plot eigenvectors of covariance of samples
    eig, eigv = tf_KL_decomposition(prior_cov_samples, cov_samples)
    eig, eigv = eig.numpy(), eigv.numpy()
    inds = (np.argsort(eig)[::-1])
    param_directions = np.linalg.inv(eigv.T)
    eigv = (param_directions.T[inds]).T

    norm0 = np.linalg.norm(eigv[:, 0])
    mode = 0
    plt.plot(maximum_posterior[0] + r*eigv[0, mode]/norm0, maximum_posterior[1] + r*eigv[1, mode]/norm0, ls='-', color='k')
    mode = 1
    norm1 = np.linalg.norm(eigv[:, 1])
    plt.plot(maximum_posterior[0] + r*eigv[0, mode]/norm1, maximum_posterior[1] + r*eigv[1, mode]/norm1, ls='-', color='k')

    plt.legend()
    plt.xlim([np.amin(P1), np.amax(P1)])
    plt.ylim([np.amin(P2), np.amax(P2)])
    plt.xlabel(param_labels_latex[0], fontsize=fontsize)
    plt.ylabel(param_labels_latex[1], fontsize=fontsize)
    plt.tight_layout()
    plt.savefig(outroot+'2_local_metric_KL.pdf')
    plt.close('all')

    ###########################################################################
    # Plots of local KL eigenvalues
    ###########################################################################

    # feedback:
    print('3) local KL eigenvalues')

    coords = np.array([X, Y], dtype=np.float32).reshape(2, -1).T

    # compute the metric at all coordinates
    local_metrics = flow.metric(coords)
    prior_local_metrics = prior_flow.metric(coords)

    # compute KL decomposition:
    KL_eig, KL_eigv = tf_KL_decomposition(local_metrics, prior_local_metrics)
    idx = np.argsort(KL_eig, axis=1)[0]
    KL_eig = KL_eig.numpy()[:, idx]
    KL_eigv = KL_eigv.numpy()[:, :, idx]

    # plot KL eigenvalues
    plt.figure(figsize=(2.4*figsize[0], figsize[1]))
    gs = gridspec.GridSpec(1, 2)
    ax1 = plt.subplot(gs[0, 0])
    ax2 = plt.subplot(gs[0, 1])

    mode = 0
    pc = ax1.pcolormesh(X, Y, np.log10(KL_eig[:, mode].reshape(200, 200)), linewidth=0, rasterized=True, shading='auto', cmap='PiYG_r', label='First mode')
    colorbar = plt.colorbar(pc, ax=ax1)
    # plot contours
    ax1.contour(X, Y, P, get_levels(P, x, y, levels_5), linewidths=1., linestyles='-', colors=['k' for i in levels_5])
    ax1.scatter(maximum_posterior[0], maximum_posterior[1], color='k')
    ax1.set_xlim([np.amin(P1), np.amax(P1)])
    ax1.set_ylim([np.amin(P2), np.amax(P2)])
    ax1.set_xlabel(param_labels_latex[0], fontsize=fontsize)
    ax1.set_ylabel(param_labels_latex[1], fontsize=fontsize)
    ax1.set_title('Mode 0')

    mode = 1
    pc = ax2.pcolormesh(X, Y, np.log10(KL_eig[:, mode].reshape(200, 200)), linewidth=0, rasterized=True, shading='auto', cmap='PiYG_r', label='Second mode')
    plt.colorbar(pc, ax=ax2)
    # plot contours
    ax2.contour(X, Y, P, get_levels(P, x, y, levels_5), linewidths=1., linestyles='-', colors=['k' for i in levels_5])
    ax2.scatter(maximum_posterior[0], maximum_posterior[1], color='k')
    ax2.set_xlim([np.amin(P1), np.amax(P1)])
    ax2.set_ylim([np.amin(P2), np.amax(P2)])
    ax2.set_xlabel(param_labels_latex[0], fontsize=fontsize)
    ax2.set_ylabel(param_labels_latex[1], fontsize=fontsize)
    ax2.set_title('Mode 1')

    plt.tight_layout()
    plt.savefig(outroot+'3_local_KL_eigs.pdf')
    plt.close('all')

    ##########################################################################
    # KL eigenvalue flow
    ##########################################################################

    def _naive_KL_ode(t, y, reference, flow, prior_flow):
        """
        Solve naively the dynamical equation for KL decomposition in abstract space.
        """
        # preprocess:
        x = tf.convert_to_tensor([tf.cast(y, tf.float32)])
        # compute metrics:
        metric = flow.metric(x)[0]
        prior_metric = prior_flow.metric(x)[0]
        # compute KL decomposition:
        eig, eigv = tf_KL_decomposition(metric, prior_metric)
        # normalize to one to project and select direction:
        temp = tf.matmul(tf.transpose(eigv), tf.transpose([reference]))[:, 0] / tf.linalg.norm(eigv, axis=0)
        idx = tf.math.argmax(tf.abs(temp))
        w = tf.math.sign(temp[idx]) * eigv[:, idx]
        # normalize affine parameter:
        s = tf.math.sqrt(tf.tensordot(w, tf.tensordot(metric, w, 1), 1))
        #
        return tf.convert_to_tensor([w / s])

    def solve_KL_ode(flow, prior_flow, y0, n, length=1.5, side='both', integrator_options=None, num_points=100, **kwargs):
        """
        Solve eigenvalue problem in abstract space
        side = '+', '-', 'both'
        length = 1.5
        num_points = 100
        n=0
        """
        # define solution points:
        solution_times = tf.linspace(0., length, num_points)
        # compute initial KL decomposition:
        x = tf.convert_to_tensor([tf.cast(y0, tf.float32)])
        metric = flow.metric(x)[0]
        prior_metric = prior_flow.metric(x)[0]
        # compute KL decomposition:
        eig, eigv = tf_KL_decomposition(metric, prior_metric)
        # solve forward:
        if side == '+' or side == 'both':
            # initialize solution:
            temp_sol_1 = np.zeros((num_points-1, flow.num_params))
            temp_sol_dot_1 = np.zeros((num_points-1, flow.num_params))
            # initialize forward integration:
            solver = scipy.integrate.ode(_naive_KL_ode)
            if integrator_options is not None:
                solver.set_integrator(**integrator_options)
            solver.set_initial_value(y0, 0.)
            reference = eigv[:, n] / tf.norm(eigv[:, n])
            yt = y0.numpy()
            yprime = eigv[:, n]
            # do the time steps:
            for ind, t in enumerate(solution_times[1:]):
                # set the reference:
                solver.set_f_params(reference, flow, prior_flow)
                # advance solver:
                try:
                    yt = solver.integrate(t)
                    yprime = _naive_KL_ode(t, yt, reference, flow, prior_flow)
                except:
                    pass
                # update reference:
                reference = yprime[0] / tf.norm(yprime[0])
                # save out:
                temp_sol_1[ind] = yt.copy()
                temp_sol_dot_1[ind] = yprime.numpy().copy()
            # return if needed:
            if side == '+':
                traj = np.concatenate((x.numpy(), temp_sol_1))
                vel = np.concatenate(([eigv[:, n].numpy()], temp_sol_dot_1))
                return solution_times, traj, vel
        # solve backward:
        if side == '-' or side == 'both':
            # initialize solution:
            temp_sol_2 = np.zeros((num_points-1, flow.num_params))
            temp_sol_dot_2 = np.zeros((num_points-1, flow.num_params))
            # initialize backward integration:
            solver = scipy.integrate.ode(_naive_KL_ode)
            if integrator_options is not None:
                solver.set_integrator(**integrator_options)
            solver.set_initial_value(y0, 0.)
            reference = - eigv[:, n] / tf.norm(eigv[:, n])
            yt = y0.numpy()
            yprime = reference
            for ind, t in enumerate(solution_times[1:]):
                # set the reference:
                solver.set_f_params(reference, flow, prior_flow)
                # advance solver:
                try:
                    yt = solver.integrate(t)
                    yprime = _naive_KL_ode(t, yt, reference, flow, prior_flow)
                except:
                    pass
                # update reference:
                reference = yprime[0] / tf.norm(yprime[0])
                # save out:
                temp_sol_2[ind] = yt.copy()
                temp_sol_dot_2[ind] = yprime.numpy().copy()
            # return if needed:
            if side == '-':
                traj = np.concatenate((temp_sol_2[::-1], x.numpy()))
                vel = np.concatenate((-temp_sol_dot_2[::-1], [eigv[:, n].numpy()]))
                return -solution_times, traj, vel
        # patch solutions:
        times = np.concatenate((-solution_times[::-1], solution_times[1:]))
        traj = np.concatenate((temp_sol_2[::-1], x.numpy(), temp_sol_1))
        vel = np.concatenate((-temp_sol_dot_2[::-1], [eigv[:, n].numpy()], temp_sol_dot_1))
        #
        return times, traj, vel

    # lines along the global principal components:
    y0 = flow.cast(reference_point)
    length = (flow.sigma_to_length(3)).astype(np.float32)

    _, temp_start_1, __ = solve_KL_ode(flow, prior_flow, flow.cast(y0), n=0, length=length, num_points=101, side='+')
    _, temp_start_2, __ = solve_KL_ode(flow, prior_flow, flow.cast(y0), n=0, length=length, num_points=101, side='-')
    start_1 = np.concatenate((temp_start_2[::101//5][:-1], temp_start_1[::101//5]))

    _, temp_start_1, __ = solve_KL_ode(flow, prior_flow, flow.cast(y0), n=1, length=length, num_points=101, side='+')
    _, temp_start_2, __ = solve_KL_ode(flow, prior_flow, flow.cast(y0), n=1, length=length, num_points=101, side='-')
    start_0 = np.concatenate((temp_start_2[::101//5][:-1], temp_start_1[::101//5]))

    # solve:
    modes_0, modes_1 = [], []
    for start in start_0:
        _, mode, _ = solve_KL_ode(flow, prior_flow, flow.cast(start), n=0, length=length, num_points=100)
        modes_0.append(mode)
    for start in start_1:
        _, mode, _ = solve_KL_ode(flow, prior_flow, flow.cast(start), n=1, length=length, num_points=100)
        modes_1.append(mode)
    # plot:
    plt.figure(figsize=(2*figsize[0], figsize[1]))
    gs = gridspec.GridSpec(1, 2)
    ax1 = plt.subplot(gs[0, 0])
    ax2 = plt.subplot(gs[0, 1])

    for mode in modes_0:
        ax1.plot(mode[:, 0], mode[:, 1], lw=1., ls='-', color='k')
    for mode in modes_1:
        ax1.plot(mode[:, 0], mode[:, 1], lw=1., ls='-', color='red')

    ax1.contour(X, Y, P, get_levels(P, x, y, levels_3), linewidths=2., linestyles='-', colors=['blue' for i in levels_5], zorder=999)
    ax1.scatter(maximum_posterior[0], maximum_posterior[1], color='k')

    ax1.set_xlim([np.amin(P1), np.amax(P1)])
    ax1.set_ylim([np.amin(P2), np.amax(P2)])
    ax1.set_xlabel(param_labels_latex[0], fontsize=fontsize)
    ax1.set_ylabel(param_labels_latex[1], fontsize=fontsize)

    for mode in modes_0:
        mode_abs = flow.map_to_abstract_coord(mode.astype(np.float32))
        ax2.plot(*np.array(mode_abs).T, lw=1., ls='-', color='k')
    for mode in modes_1:
        mode_abs = flow.map_to_abstract_coord(mode.astype(np.float32))
        ax2.plot(*np.array(mode_abs).T, lw=1., ls='-', color='red')

    # print the iso-contours:
    origin = [0,0]
    theta = np.linspace(0.0, 2.*np.pi, 200)
    for i in range(4):
        _length = np.sqrt(scipy.stats.chi2.isf(1.-utilities.from_sigma_to_confidence(i), 2))
        ax2.plot(origin[0]+_length*np.sin(theta), origin[1]+_length*np.cos(theta), ls='--', lw=2., color='blue')
    y0_abs = flow.map_to_abstract_coord(y0)
    ax2.scatter(y0_abs[0], y0_abs[1], color='k', zorder=999)

    ax2.set_xlabel('$Z_{1}$', fontsize=fontsize)
    ax2.set_ylabel('$Z_{2}$', fontsize=fontsize)

    plt.tight_layout()
    plt.savefig(outroot+'4_local_KL_flow.pdf')
