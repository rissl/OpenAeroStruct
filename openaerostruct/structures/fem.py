"""Define the LinearSystemComp class."""
from __future__ import division, print_function

from six.moves import range

import numpy as np
from scipy import linalg

from openmdao.core.implicitcomponent import ImplicitComponent


class FEM(ImplicitComponent):
    """
    Component that solves a linear system, Ax=b.

    Designed to handle small, dense linear systems (Ax=B) that can be efficiently solved with
    lu-decomposition. It can be vectorized to either solve for multiple right hand sides,
    or to solve multiple linear systems.

    Attributes
    ----------
    _lup : None or list(object)
        matrix factorizations returned from scipy.linag.lu_factor for each A matrix
    """

    def __init__(self, **kwargs):
        """
        Intialize the LinearSystemComp component.

        Parameters
        ----------
        **kwargs : dict of keyword arguments
            Keyword arguments that will be mapped into the Component options.
        """
        super(FEM, self).__init__(**kwargs)
        self._lup = None

    def initialize(self):
        """
        Declare options.
        """
        self.options.declare('size', default=1, types=int, desc='The size of the linear system.')
        self.options.declare('vec_size', types=int, default=1,
                             desc='Number of linear systems to solve.')
        self.options.declare('vectorize_A', default=False, types=bool,
                             desc='Set to True to vectorize the A matrix.')

    def setup(self):
        """
        Matrix and RHS are inputs, solution vector is the output.
        """
        vec_size = self.options['vec_size']
        vec_size_A = self.vec_size_A = vec_size if self.options['vectorize_A'] else 1
        size = self.options['size']
        mat_size = size * size
        full_size = size * vec_size

        self._lup = []
        shape = (vec_size, size) if vec_size > 1 else (size, )
        shape_A = (vec_size_A, size, size) if vec_size_A > 1 else (size, size)

        init_A = np.eye(size)

        self.add_input('K', val=init_A, units='N/m')
        self.add_input('forces', val=np.ones(shape), units='N')
        self.add_output('disp_aug', shape=shape, val=.1, units='m')

        # Set up the derivatives.
        row_col = np.arange(full_size, dtype="int")

        self.declare_partials('disp_aug', 'forces', val=np.full(full_size, -1.0), rows=row_col, cols=row_col)

        rows = np.repeat(np.arange(full_size), size)

        cols = np.tile(np.arange(mat_size), vec_size)

        self.declare_partials('disp_aug', 'K', rows=rows, cols=cols)

        cols = np.tile(np.arange(size), size)
        cols = np.tile(cols, vec_size) + np.repeat(np.arange(vec_size), mat_size) * size

        self.declare_partials(of='disp_aug', wrt='disp_aug', rows=rows, cols=cols)

    def apply_nonlinear(self, inputs, outputs, residuals):
        """
        R = Ax - b.

        Parameters
        ----------
        inputs : Vector
            unscaled, dimensional input variables read via inputs[key]
        outputs : Vector
            unscaled, dimensional output variables read via outputs[key]
        residuals : Vector
            unscaled, dimensional residuals written to via residuals[key]
        """
        residuals['disp_aug'] = inputs['K'].dot(outputs['disp_aug']) - inputs['forces']

    def solve_nonlinear(self, inputs, outputs):
        """
        Use numpy to solve Ax=b for x.

        Parameters
        ----------
        inputs : Vector
            unscaled, dimensional input variables read via inputs[key]
        outputs : Vector
            unscaled, dimensional output variables read via outputs[key]
        """
        vec_size = self.options['vec_size']
        vec_size_A = self.vec_size_A

        # lu factorization for use with solve_linear
        self._lup = []
        self._lup = linalg.lu_factor(inputs['K'])
        outputs['disp_aug'] = linalg.lu_solve(self._lup, inputs['forces'])

    def linearize(self, inputs, outputs, J):
        """
        Compute the non-constant partial derivatives.

        Parameters
        ----------
        inputs : Vector
            unscaled, dimensional input variables read via inputs[key]
        outputs : Vector
            unscaled, dimensional output variables read via outputs[key]
        J : Jacobian
            sub-jac components written to jacobian[output_name, input_name]
        """
        x = outputs['disp_aug']
        size = self.options['size']
        vec_size = self.options['vec_size']

        J['disp_aug', 'K'] = np.tile(x, size).flat
        J['disp_aug', 'disp_aug'] = np.tile(inputs['K'].flat, vec_size)

    def solve_linear(self, d_outputs, d_residuals, mode):
        r"""
        Back-substitution to solve the derivatives of the linear system.

        If mode is:
            'fwd': d_residuals \|-> d_outputs

            'rev': d_outputs \|-> d_residuals

        Parameters
        ----------
        d_outputs : Vector
            unscaled, dimensional quantities read via d_outputs[key]
        d_residuals : Vector
            unscaled, dimensional quantities read via d_residuals[key]
        mode : str
            either 'fwd' or 'rev'
        """
        vec_size = self.options['vec_size']
        vec_size_A = self.vec_size_A

        if mode == 'fwd':
            if vec_size > 1:
                for j in range(vec_size):
                    idx = j if vec_size_A > 1 else 0
                    d_outputs['disp_aug'][j] = linalg.lu_solve(self._lup[idx], d_residuals['disp_aug'][j],
                                                        trans=0)
            else:
                d_outputs['disp_aug'] = linalg.lu_solve(self._lup, d_residuals['disp_aug'], trans=0)

        else:  # rev
            if vec_size > 1:
                for j in range(vec_size):
                    idx = j if vec_size_A > 1 else 0
                    d_residuals['disp_aug'][j] = linalg.lu_solve(self._lup[idx], d_outputs['disp_aug'][j],
                                                          trans=1)
            else:
                d_residuals['disp_aug'] = linalg.lu_solve(self._lup, d_outputs['disp_aug'], trans=1)
