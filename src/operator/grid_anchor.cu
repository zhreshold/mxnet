/*!
 * Copyright (c) 2016 by Contributors
 * \file gird_anchor.cc
 * \brief generate grid anchors cuda impl
 * \author Joshua Zhang
*/

#include "./grid_anchor-inl.h"

#define WARPS_PER_BLOCK 1
#define THREADS_PER_WARP 32

#define GRIDANCHOR_CUDA_CHECK(condition) \
  /* Code block avoids redefinition of cudaError_t error */ \
  do { \
    cudaError_t error = condition; \
    CHECK_EQ(error, cudaSuccess) << " " << cudaGetErrorString(error); \
  } while (0)

namespace mshadow {
namespace cuda {
template<typename DType>
__global__ void AssignCenters(DType *out, int in_width, int in_height,
                              float step_x, float step_y) {
  int index = blockIdx.x * blockDim.x + threadIdx.x;
  if (index >= in_width * in_height) return;
  int r = index / in_width;
  int c = index % in_width;
  float center_x = (c + 0.5) * step_x;
  float center_y = (r + 0.5) * step_y;
  DType *ptr = out + index;
  *ptr = center_x;  // x
  ptr += in_width * in_height;
  *ptr = center_y;  // y
}

template<typename DType>
__global__ void AssignBoxes(DType *out, float size, float sqrt_ratio,
                              int in_width, int in_height, float step_x,
                              float step_y) {
  int index = blockIdx.x * blockDim.x + threadIdx.x;
  if (index >= in_width * in_height) return;
  int r = index / in_width;
  int c = index % in_width;
  float center_x = (c + 0.5) * step_x;
  float center_y = (r + 0.5) * step_y;
  float w = size * sqrt_ratio / 2;  // half width
  float h = size / sqrt_ratio / 2;  // half height
  DType *ptr = out + index;
  *ptr = center_x - w;  // xmin
  ptr += in_width * in_height;
  *ptr = center_y - h;  // ymin
  ptr += in_width * in_height;
  *ptr = center_x + w;  // xmax
  ptr += in_width * in_height;
  *ptr = center_y + h;  // ymax
}

template<typename DType>
__global__ void PrintOutput(DType *ptr, int num) {
  for (int i = 0; i < num; ++i) {
    printf("%d: %f, ", i, float(ptr[i]));
  }
}
}  // namespace cuda

template<typename DType>
inline void GridAnchorForward(const Tensor<gpu, 3, DType> &out,
                              int in_width, int in_height,
                              const std::vector<float> &sizes,
                              const std::vector<float> &ratios) {
  CHECK_EQ(out.CheckContiguous(), true);
  cudaStream_t stream = Stream<gpu>::GetStream(out.stream_);
  DType *out_ptr = out.dptr_;
  float step_x = 1.f / in_width;
  float step_y = 1.f / in_height;
  int num_sizes = static_cast<int>(sizes.size());
  int num_ratios = static_cast<int>(ratios.size());

  int num_thread = THREADS_PER_WARP * WARPS_PER_BLOCK;
  dim3 thread_dim(num_thread);
  dim3 block_dim((in_width * in_height - 1) / num_thread + 1);

  cuda::AssignCenters<DType><<<block_dim, thread_dim, 0, stream>>>(out_ptr,
    in_width, in_height, step_x, step_y);
  GRIDANCHOR_CUDA_CHECK(cudaPeekAtLastError());
  out_ptr += 2 * in_width * in_height;

  for (int i = 0; i < num_sizes; ++i) {
    float size = sizes[i];
    for (int j = 0; j < num_ratios; ++j) {
      float ratio = sqrtf(ratios[j]);
      cuda::AssignBoxes<DType><<<block_dim, thread_dim, 0, stream>>>(out_ptr,
        size, ratio, in_width, in_height, step_x, step_y);
      out_ptr += 4 * in_width * in_height;
    }
  }
  GRIDANCHOR_CUDA_CHECK(cudaPeekAtLastError());

  // cuda::PrintOutput<DType><<<1,1>>>(out.dptr_, in_width * in_height);
  // LOG(INFO) << "Y:";
  // cuda::PrintOutput<DType><<<1,1>>>(out.dptr_ + in_width * in_height,
  //   in_width * in_height);
}
}  // namespace mshadow

namespace mxnet {
namespace op {
template<>
Operator* CreateOp<gpu>(GridAnchorParam param, int dtype) {
  Operator *op = NULL;
  MSHADOW_REAL_TYPE_SWITCH(dtype, DType, {
    op = new GridAnchorOp<gpu, DType>(param);
  });
  return op;
}

}  // namespace op
}  // namespace mxnet
