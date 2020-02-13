import lab.torch as B
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
import wbml.plot
from stheno import EQ
from varz import Vars
from varz.torch import minimise_l_bfgs_b
from wbml.data.eeg import load
from wbml.experiment import WorkingDirectory
from wbml.lmm import LMMPP

wbml.out.report_time = True
wd = WorkingDirectory('_experiments', 'eeg_ilmm')

_, train, test = load()

x = np.array(train.index)
y = np.array(train)

# Normalise data.
y_mean = np.nanmean(y, keepdims=True, axis=0)
y_scale = np.nanstd(y, keepdims=True, axis=0)
y_norm = (y - y_mean) / y_scale

p = B.shape(y)[1]
m = 3
vs = Vars(torch.float64)


def construct_model(vs):
    # Construct model for the latent processes.
    kernels = [vs.pos(1, name=f'{i}/var') *
               EQ().stretch(vs.pos(0.02, name=f'{i}/scale'))
               for i in range(m)]
    noise = vs.pos(1e-2, name='noise')
    latent_noise = vs.pos(1e-2 * B.ones(3), name='latent_noise')
    H = vs.get(shape=(p, m), name='h')

    # Construct ILMM.
    return LMMPP(kernels, noise, latent_noise, H)


def objective(vs):
    return -construct_model(vs).logpdf(torch.tensor(x),
                                       torch.tensor(y_norm))


minimise_l_bfgs_b(objective, vs, trace=True, iters=1000)

# Predict.
model = construct_model(vs)
model = model.condition(torch.tensor(x), torch.tensor(y_norm))
preds, _, _ = model.marginals(torch.tensor(x))
means, lowers, uppers = B.to_numpy([B.stack(*xs, axis=1) for xs in zip(*preds)])

# Undo normalisation
means = means * y_scale + y_mean
lowers = lowers * y_scale + y_mean
uppers = uppers * y_scale + y_mean

# Compute SMSE.
pred = pd.DataFrame(means, index=train.index, columns=train.columns)
smse = ((pred - test) ** 2).mean().mean() / \
       ((test.mean(axis=0) - test) ** 2).mean().mean()

# Report and save average SMSE.
wbml.out.kv('SMSE', smse)
with open(wd.file('smse.txt'), 'w') as f:
    f.write(str(smse))

# Name of output to plot.
name = 'F2'

# Plot the result.
plt.figure(figsize=(12, 2))
wbml.plot.tex()

p = list(train.columns).index(name)
plt.plot(x, means[:, p], c='tab:blue')
plt.fill_between(x, lowers[:, p], uppers[:, p],
                 facecolor='tab:blue', alpha=.25)
plt.scatter(x, y[:, p], c='tab:green', marker='x', s=10)
plt.scatter(test[name].index, test[name], c='tab:orange', marker='x', s=10)
plt.xlabel('Time (second)')
plt.xlim(0.4, 1)
plt.ylabel(f'{name} (volt)')
wbml.plot.tweak(legend=False)

plt.tight_layout()
plt.savefig(wd.file('eeg.pdf'))
plt.show()
