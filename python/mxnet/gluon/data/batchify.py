# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

# coding: utf-8
# pylint: disable=
"""Batchify function."""
from __future__ import absolute_import

import numpy as np

from ...context import Context, cpu
from ... import ndarray as nd
from ... import numpy as _np
from ...util import is_np_array

class Stack(object):
    r"""Stack the input data samples to construct the batch.
    The N input samples must have the same shape/length and will be stacked to construct a batch.
    Examples
    --------
    >>> from gluoncv.data import batchify
    >>> # Stack multiple lists
    >>> a = [1, 2, 3, 4]
    >>> b = [4, 5, 6, 8]
    >>> c = [8, 9, 1, 2]
    >>> batchify.Stack()([a, b, c])
    [[1. 2. 3. 4.]
     [4. 5. 6. 8.]
     [8. 9. 1. 2.]]
    <NDArray 3x4 @cpu(0)>
    >>> # Stack multiple numpy.ndarrays
    >>> import numpy as np
    >>> a = np.array([[1, 2, 3, 4], [5, 6, 7, 8]])
    >>> b = np.array([[5, 6, 7, 8], [1, 2, 3, 4]])
    >>> batchify.Stack()([a, b])
    [[[1. 2. 3. 4.]
      [5. 6. 7. 8.]]
     [[5. 6. 7. 8.]
      [1. 2. 3. 4.]]]
    <NDArray 2x2x4 @cpu(0)>
    >>> # Stack multiple NDArrays
    >>> import mxnet as mx
    >>> a = nd.array([[1, 2, 3, 4], [5, 6, 7, 8]])
    >>> b = nd.array([[5, 6, 7, 8], [1, 2, 3, 4]])
    >>> batchify.Stack()([a, b])
    [[[1. 2. 3. 4.]
      [5. 6. 7. 8.]]
     [[5. 6. 7. 8.]
      [1. 2. 3. 4.]]]
    <NDArray 2x2x4 @cpu(0)>
    """
    def __init__(self, use_shared_mem=False):
        self._use_shared_mem = use_shared_mem

    def __call__(self, data):
        """Batchify the input data
        Parameters
        ----------
        data : list
            The input data samples
        Returns
        -------
        batch_data : NDArray
        """
        _arr = _np if is_np_array() else nd
        if isinstance(data[0], _arr.NDArray):
            dtype = data[0].dtype
            if self._use_shared_mem:
                out = _arr.empty((len(data),) + data[0].shape, dtype=dtype,
                                  ctx=Context('cpu_shared', 0))
                return _arr.stack(*data, out=out)
            else:
                return _arr.stack(*data)
        elif isinstance(data[0], (tuple, list)):
            data = zip(*data)
            return [self.__call__(i) for i in data]
        else:
            out = np.asarray(data)
            dtype = out.dtype
            if self._use_shared_mem:
                return _arr.array(out, ctx=Context('cpu_shared', 0), dtype=dtype)
            else:
                return _arr.array(out, dtype=dtype)

    def __mx_handle__(self):
        from ._internal import StackBatchify
        return StackBatchify()

def _pad_arrs_to_max_length(arrs, pad_axis, pad_val, use_shared_mem, dtype):
    """Inner Implementation of the Pad batchify
    Parameters
    ----------
    arrs : list
    pad_axis : int
    pad_val : number
    use_shared_mem : bool, default False
    Returns
    -------
    ret : NDArray
    original_length : NDArray
    """
    _arr = _np if is_np_array() else nd
    if isinstance(arrs[0], _arr.NDArray):
        dtype = arrs[0].dtype if dtype is None else dtype
        arrs = [arr.asnumpy() for arr in arrs]
    elif not isinstance(arrs[0], np.ndarray):
        arrs = [np.asarray(ele) for ele in arrs]
    else:
        dtype = arrs[0].dtype if dtype is None else dtype

    original_length = [ele.shape[pad_axis] for ele in arrs]
    max_size = max(original_length)

    ret_shape = list(arrs[0].shape)
    ret_shape[pad_axis] = max_size
    ret_shape = (len(arrs), ) + tuple(ret_shape)

    ret = np.full(shape=ret_shape, fill_value=pad_val, dtype=dtype)

    for i, arr in enumerate(arrs):
        if arr.shape[pad_axis] == max_size:
            ret[i] = arr
        else:
            slices = [slice(None) for _ in range(arr.ndim)]
            slices[pad_axis] = slice(0, arr.shape[pad_axis])
            if slices[pad_axis].start != slices[pad_axis].stop:
                slices = [slice(i, i + 1)] + slices
                ret[tuple(slices)] = arr

    ctx = Context('cpu_shared', 0) if use_shared_mem else cpu()
    ret = _arr.array(ret, ctx=ctx, dtype=dtype)
    original_length = _arr.array(original_length, ctx=ctx, dtype=np.int32)

    return ret, original_length


class Pad(object):
    """Pad the input ndarrays along the specific padding axis and stack them to get the output.
    Input of the function will be N samples. Each sample should contain a single element that
    can be 1) numpy.ndarray, 2) mxnet.nd.NDArray, 3) list of numbers.
    You can set the `axis` and `pad_val` to determine the padding axis and
    value.
    The arrays will be padded to the largest dimension at `axis` and then
    stacked to form the final output. In addition, the function will output the original dimensions
    at the `axis` if ret_length is turned on.
    Parameters
    ----------
    axis : int or tuple, default 0
        The axis to pad the arrays. The arrays will be padded to the largest dimension at
        pad_axis. For example, assume the input arrays have shape
        (10, 8, 5), (6, 8, 5), (3, 8, 5) and the pad_axis is 0. Each input will be padded into
        (10, 8, 5) and then stacked to form the final output.
    pad_val : float or int, default None
        The padding value.
    ret_length : bool, default False
        Whether to return the valid length in the output.
    dtype : str or numpy.dtype, default None
        The value type of the output. If it is set to None, the input data type is used.
    Examples
    --------
    >>> from gluoncv.data import batchify
    >>> # Inputs are multiple lists
    >>> a = [1, 2, 3, 4]
    >>> b = [4, 5, 6]
    >>> c = [8, 2]
    >>> batchify.Pad()([a, b, c])
    [[ 1  2  3  4]
     [ 4  5  6  0]
     [ 8  2  0  0]]
    <NDArray 3x4 @cpu(0)>
    >>> # Also output the lengths
    >>> a = [1, 2, 3, 4]
    >>> b = [4, 5, 6]
    >>> c = [8, 2]
    >>> batchify.Pad(ret_length=True)([a, b, c])
    (
     [[1 2 3 4]
      [4 5 6 0]
      [8 2 0 0]]
     <NDArray 3x4 @cpu(0)>,
     [4 3 2]
     <NDArray 3 @cpu(0)>)
    >>> # Inputs are multiple ndarrays
    >>> import numpy as np
    >>> a = np.array([[1, 2, 3, 4], [5, 6, 7, 8]])
    >>> b = np.array([[5, 8], [1, 2]])
    >>> batchify.Pad(axis=1, pad_val=-1)([a, b])
    [[[ 1  2  3  4]
      [ 5  6  7  8]]
     [[ 5  8 -1 -1]
      [ 1  2 -1 -1]]]
    <NDArray 2x2x4 @cpu(0)>
    >>> # Inputs are multiple NDArrays
    >>> import mxnet as mx
    >>> a = nd.array([[1, 2, 3, 4], [5, 6, 7, 8]])
    >>> b = nd.array([[5, 8], [1, 2]])
    >>> batchify.Pad(axis=1, pad_val=-1)([a, b])
    [[[ 1.  2.  3.  4.]
      [ 5.  6.  7.  8.]]
     [[ 5.  8. -1. -1.]
      [ 1.  2. -1. -1.]]]
    <NDArray 2x2x4 @cpu(0)>
    """
    def __init__(self, axis=0, pad_val=None, ret_length=False, dtype=None, use_shared_mem=False):
        self._axis = axis
        assert isinstance(axis, int), 'axis must be an integer! ' \
                                      'Received axis=%s, type=%s.' % (str(axis),
                                                                      str(type(axis)))
        self._pad_val = 0 if pad_val is None else pad_val
        self._ret_length = ret_length
        self._dtype = dtype
        self._warned = False
        self._use_shared_mem = use_shared_mem

        if pad_val is None:
            warnings.warn(
                'Padding value is not given and will be set automatically to 0 '
                'in data.batchify.Pad(). '
                'Please check whether this is intended '
                '(e.g. value of padding index in the vocabulary).')

    def __call__(self, data):
        """Batchify the input data.
        The input can be list of numpy.ndarray, list of numbers or list of
        mxnet.nd.NDArray. Inputting mxnet.nd.NDArray is discouraged as each
        array need to be converted to numpy for efficient padding.
        The arrays will be padded to the largest dimension at `axis` and then
        stacked to form the final output. In addition, the function will output
        the original dimensions at the `axis` if ret_length is turned on.
        Parameters
        ----------
        data : List[np.ndarray] or List[List[dtype]] or List[nd.NDArray]
            List of samples to pad and stack.
        Returns
        -------
        batch_data: NDArray
            Data in the minibatch. Shape is (N, ...)
        valid_length: NDArray, optional
            The sequences' original lengths at the padded axis. Shape is (N,). This will only be
            returned in `ret_length` is True.
        """
        _arr = _np if is_np_array() else nd
        if isinstance(data[0], _arr.NDArray) and not self._warned:
            self._warned = True
            warnings.warn(
                'Using Pad with NDArrays is discouraged for speed reasons. '
                'Instead you should pad your data while it is still a list '
                'and before converting to an NDArray. '
                'Alternatively you can consider inputting a numpy.ndarray.')
        if isinstance(data[0], (_arr.NDArray, np.ndarray, list)):
            padded_arr, original_length = _pad_arrs_to_max_length(data, self._axis,
                                                                  self._pad_val, self._use_shared_mem,
                                                                  self._dtype)
            if self._ret_length:
                return padded_arr, original_length
            else:
                return padded_arr
        else:
            raise NotImplementedError(
                "Pad() does not support multiple items, use Group(Pad(), Pad(), ...) instead")

def _append_arrs(arrs, use_shared_mem=False, expand=False, batch_axis=0):
    """Internal impl for returning appened arrays as list."""
    _arr = _np if is_np_array() else nd
    if isinstance(arrs[0], _arr.NDArray):
        if use_shared_mem:
            out = [x.as_in_context(Context('cpu_shared', 0)) for x in arrs]
        else:
            out = arrs
    else:
        if use_shared_mem:
            out = [_arr.array(x, ctx=Context('cpu_shared', 0)) for x in arrs]
        else:
            out = [_arr.array(x) for x in arrs]

    # add batch axis
    if expand:
        out = [x.expand_dims(axis=batch_axis) for x in out]
    return out


class Append(object):
    r"""Loosely return list of the input data samples.
    There is no constraint of shape for any of the input samples, however, you will
    only be able to apply single batch operations since the output have different shapes.
    Examples
    --------
    >>> a = [1, 2, 3, 4]
    >>> b = [4, 5, 6]
    >>> c = [8, 2]
    >>> batchify.Append()([a, b, c])
    [
    [[1. 2. 3. 4.]]
    <NDArray 1x4 @cpu_shared(0)>,
    [[4. 5. 6.]]
    <NDArray 1x3 @cpu_shared(0)>,
    [[8. 2.]]
    <NDArray 1x2 @cpu_shared(0)>
    ]
    """

    def __init__(self, expand=True, batch_axis=0, use_shared_mem=False):
        self._expand = expand
        self._batch_axis = batch_axis
        self._use_shared_mem = use_shared_mem

    def __call__(self, data):
        """Batchify the input data.
        Parameters
        ----------
        data : list
            The input data samples
        Returns
        -------
        batch_data : NDArray
        """
        return _append_arrs(data, use_shared_mem=self._use_shared_mem,
                            expand=self._expand, batch_axis=self._batch_axis)

class Group:
    """Wrap multiple batchify functions together. The input functions will be applied
    to the corresponding input fields.
    Each data sample should be a list or tuple containing multiple attributes. The `i`th batchify
    function stored in `Group` will be applied on the `i`th attribute. For example, each
    data sample is (nd_data, label). You can wrap two batchify functions using
    `Group(DataBatchify, LabelBatchify)` to batchify nd_data and label correspondingly.
    Parameters
    ----------
    fn : list or tuple or callable
        The batchify functions to wrap.
    *args : tuple of callable
        The additional batchify functions to wrap.
    Examples
    --------
    >>> a = ([1, 2, 3, 4], 0)
    >>> b = ([5, 7], 1)
    >>> c = ([1, 2, 3, 4, 5, 6, 7], 0)
    >>> f1, f2 = Group(Pad(pad_val=0),
    ...                Stack())([a, b])
    >>> f1
    <BLANKLINE>
    [[1. 2. 3. 4.]
     [5. 7. 0. 0.]]
    <NDArray 2x4 @cpu_shared(0)>
    >>> f2
    <BLANKLINE>
    [0 1]
    <NDArray 2 @cpu_shared(0)>
    """
    def __init__(self, fn, *args):
        if isinstance(fn, (list, tuple)):
            assert len(args) == 0, 'Input pattern not understood. The input of Group can be ' \
                                   'Group(A, B, C) or Group([A, B, C]) or Group((A, B, C)). ' \
                                   'Received fn=%s, args=%s' % (str(fn), str(args))
            self._fn = fn
        else:
            self._fn = (fn, ) + args
        for i, ele_fn in enumerate(self._fn):
            assert hasattr(ele_fn, '__call__'), 'Batchify functions must be callable! ' \
                                                'type(fn[%d]) = %s' % (i, str(type(ele_fn)))

    def __call__(self, data):
        """Batchify the input data.
        Parameters
        ----------
        data : list
            The samples to batchfy. Each sample should contain N attributes.
        Returns
        -------
        ret : tuple
            A tuple of length N. Contains the batchified result of each attribute in the input.
        """
        assert len(data[0]) == len(self._fn),\
            'The number of attributes in each data sample should contains' \
            ' {} elements'.format(len(self._fn))
        ret = []
        for i, ele_fn in enumerate(self._fn):
            ret.append(ele_fn([ele[i] for ele in data]))
        return tuple(ret)


class AsList:
    """Simply forward the list of input data.
    This is particularly useful when the Dataset contains textual data
    and in conjonction with the `Group` batchify function.
    Examples
    --------
    >>> a = ([1, 2, 3, 4], "I am using MXNet")
    >>> b = ([5, 7, 2, 5], "Gluon rocks!")
    >>> c = ([1, 2, 3, 4], "Batchification!")
    >>> _, l = Group(Stack(), AsList())([a, b, c])
    >>> l
    ['I am using MXNet', 'Gluon rocks!', 'Batchification!']
    """
    def __call__(self, data):
        """
        Parameters
        ----------
        data : list
            The list of samples
        Returns
        -------
        ret : list
            The input list
        """
        return list(data)