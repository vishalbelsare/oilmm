from lab import B
from matrix import AbstractMatrix
from plum import Dispatcher, Referentiable, Self
from stheno import GP, Delta, Graph, Obs

__all__ = ['ILMMPP']


def _per_output(x, y):
    p = B.shape(y)[1]

    for i in range(p):
        yi = y[:, i]

        # Only return available observations.
        available = ~B.isnan(yi)

        yield x[available], i, yi[available]


def _matmul(a, x):
    n, m = B.shape(a)
    out = [0 for _ in range(n)]
    for i in range(n):
        for j in range(m):
            out[i] += a[i, j] * x[j]
    return out


class ILMMPP(metaclass=Referentiable):
    """Probabilistic programming implementation of the Instantaneous Linear
    Mixing Model.

    Args:
        kernels (list[:class:`stheno.Kernel`]) Kernels.
        h (matrix): Mixing matrix.
        noise_obs (scalar): Observation noise. One.
        noises_latent (vector): Latent noises.
    """
    _dispatch = Dispatcher(in_class=Self)

    @_dispatch(list, AbstractMatrix, B.Numeric, B.Numeric)
    def __init__(self, kernels, h, noise_obs, noises_latent):
        graph = Graph()

        # Create latent processes.
        xs = [GP(k, graph=graph) for k in kernels]
        ILMMPP.__init__(self, graph, xs, h, noise_obs, noises_latent)

    @_dispatch(Graph, list, AbstractMatrix, B.Numeric, B.Numeric)
    def __init__(self, graph, xs, h, noise_obs, noises_latent):
        self.graph = graph
        self.xs = xs
        self.h = h
        self.noise_obs = noise_obs
        self.noises_latent = noises_latent

        # Create noisy latent processes.
        xs_noisy = [x + GP(self.noises_latent[i] * Delta(), graph=self.graph)
                    for i, x in enumerate(xs)]

        # Create noiseless observed processes.
        self.fs = _matmul(self.h, self.xs)

        # Create observed processes.
        fs_noisy = _matmul(self.h, xs_noisy)
        self.ys = [f + GP(self.noise_obs * Delta(), graph=self.graph)
                   for f in fs_noisy]

    def logpdf(self, x, y):
        """Compute the logpdf of data.

        Args:
            x (tensor): Input locations.
            y (tensor): Observed values.

        Returns:
            tensor: Logpdf of data.
        """
        obs = Obs(*[(self.ys[i](x), y) for x, i, y in _per_output(x, y)])
        return self.graph.logpdf(obs)

    def condition(self, x, y):
        """Condition on data.

        Args:
            x (tensor): Input locations.
            y (tensor): Observed values.
        """
        obs = Obs(*[(self.ys[i](x), y) for x, i, y in _per_output(x, y)])
        return ILMMPP(self.graph,
                      [x | obs for x in self.xs],
                      self.h,
                      self.noise_obs,
                      self.noises_latent)

    def predict(self, x, latent=False):
        """Compute marginals.

        Args:
            x (tensor): Inputs to construct marginals at.
            latent (bool, optional): Predict noiseless processes. Defaults
                to `False`.

        Returns:
            tuple[matrix]: Tuple containing means, lower 95% central credible
                bound, and upper 95% central credible bound.
        """
        if latent:
            ps = self.fs
        else:
            ps = self.ys

        means, lowers, uppers = zip(*[p(x).marginals() for p in ps])
        return B.stack(*means, axis=1), \
               B.stack(*lowers, axis=1), \
               B.stack(*uppers, axis=1)

    def sample(self, x, latent=False):
        """Sample data.

        Args:
            x (tensor): Inputs to sample at.
            latent (bool, optional): Sample noiseless processes. Defaults to
                `False`.
        """
        if latent:
            ps = self.fs
        else:
            ps = self.ys

        samples = self.graph.sample(*[p(x) for p in ps])
        return B.concat(*samples, axis=1)
