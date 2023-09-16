
from skimage import measure
from transforms import *


class TSDFVolume:
    """Volumetric TSDF Fusion of RGB-D Images.
    """

    def __init__(self, volume_bounds, voxel_size):
        """Initialize tsdf volume instance variables.

        Args:
            volume_bounds (numpy.array [3, 2]): rows index [x, y, z] and cols index [min_bound, max_bound].
                Note: units are in meters.
            voxel_size (float): The side length of each voxel in meters.

        Raises:
            ValueError: If volume bounds are not the correct shape.
            ValueError: If voxel size is not positive.
        """
        volume_bounds = np.asarray(volume_bounds)
        if volume_bounds.shape != (3, 2):
            raise ValueError('volume_bounds should be of shape (3, 2).')

        if voxel_size <= 0.0:
            raise ValueError('voxel size must be positive.')

        # Define voxel volume parameters
        self._volume_bounds = volume_bounds
        self._voxel_size = float(voxel_size)
        self._truncation_margin = 2 * self._voxel_size  # truncation on SDF (max alowable distance away from a surface)

        # Adjust volume bounds and ensure C-order contiguous
        # and calculate voxel bounds taking the voxel size into consideration
        self._voxel_bounds = np.ceil(
            (self._volume_bounds[:, 1] - self._volume_bounds[:, 0]) / self._voxel_size
        ).copy(order='C').astype(int)
        self._volume_bounds[:, 1] = self._volume_bounds[:, 0] + self._voxel_bounds * self._voxel_size

        # volume min bound is the origin of the volume in world coordinates
        self._volume_origin = self._volume_bounds[:, 0].copy(order='C').astype(np.float32)

        print('Voxel volume size: {} x {} x {} - # voxels: {:,}'.format(
            self._voxel_bounds[0],
            self._voxel_bounds[1],
            self._voxel_bounds[2],
            self._voxel_bounds[0] * self._voxel_bounds[1] * self._voxel_bounds[2]))

        # Initialize pointers to voxel volume in memory
        self._tsdf_volume = np.ones(self._voxel_bounds).astype(np.float32)

        # for computing the cumulative moving average of observations per voxel
        self._weight_volume = np.zeros(self._voxel_bounds).astype(np.float32)
        color_bounds = np.append(self._voxel_bounds, 3)
        self._color_volume = np.zeros(color_bounds).astype(np.float32)  # rgb order

        # Get voxel grid coordinates
        xv, yv, zv = np.meshgrid(
            range(self._voxel_bounds[0]),
            range(self._voxel_bounds[1]),
            range(self._voxel_bounds[2]),
            indexing='ij')
        self._voxel_coords = np.concatenate([
            xv.reshape(1, -1),
            yv.reshape(1, -1),
            zv.reshape(1, -1)], axis=0).astype(int).T

    def get_volume(self):
        """Get the tsdf and color volumes.

        Returns:
            numpy.array [l, w, h]: l, w, h are the dimensions of the voxel grid in voxel space.
                Each entry contains the integrated tsdf value.
            numpy.array [l, w, h, 3]: l, w, h are the dimensions of the voxel grid in voxel space.
                3 is the channel number in the order r, g, then b.
        """
        return self._tsdf_volume, self._color_volume

    def get_mesh(self):
        """ Run marching cubes over the constructed tsdf volume to get a mesh representation.

        Returns:
            numpy.array [n, 3]: each row represents a 3D point.
            numpy.array [k, 3]: each row is a list of point indices used to render triangles.
            numpy.array [n, 3]: each row represents the normal vector for the corresponding 3D point.
            numpy.array [n, 3]: each row represents the color of the corresponding 3D point.
        """
        tsdf_volume, color_vol = self.get_volume()

        # Marching cubes
        voxel_points, triangles, normals, _ = measure.marching_cubes(tsdf_volume, level=0, method='lewiner')
        points_ind = np.round(voxel_points).astype(int)
        points = self.voxel_to_world(self._volume_origin, voxel_points, self._voxel_size)

        # Get vertex colors.
        rgb_vals = color_vol[points_ind[:, 0], points_ind[:, 1], points_ind[:, 2]]
        colors_r = rgb_vals[:, 0]
        colors_g = rgb_vals[:, 1]
        colors_b = rgb_vals[:, 2]
        colors = np.floor(np.asarray([colors_r, colors_g, colors_b])).T
        colors = colors.astype(np.uint8)

        return points, triangles, normals, colors

    """
    *******************************************************************************
    ****************************** ASSIGNMENT BEGINS ******************************
    *******************************************************************************
    """

    @staticmethod
    @njit(parallel=True)
    def voxel_to_world(volume_origin, voxel_coords, voxel_size):
        """ Convert from voxel coordinates to world coordinates
            (in effect scaling voxel_coords by voxel_size).

        Args:
            volume_origin (numpy.array [3, ]): The origin of the voxel
                grid in world coordinate space.
            voxel_coords (numpy.array [n, 3]): Each row gives the 3D coordinates of a voxel.
            voxel_size (float): The side length of each voxel in meters.

        Returns:
            numpy.array [n, 3]: World coordinate representation of each of the n 3D points.
        """
        volume_origin = volume_origin.astype(np.float32)
        voxel_coords = voxel_coords.astype(np.float32)
        world_points = np.empty_like(voxel_coords, dtype=np.float32)

        # NOTE: prange is used instead of range(...) to take advantage of parallelism.
        for i in prange(voxel_coords.shape[0]):
            for j in range(3):
                world_points[i][j] = volume_origin[j] + voxel_coords[i][j]*voxel_size;
            # TODO:
            #pass
        return world_points

    @staticmethod
    @njit(parallel=True)
    def get_new_tsdf_and_weights(tsdf_old, margin_distance, w_old, observation_weight):
        """[summary]

        Args:
            tsdf_old (numpy.array [v, ]): v is equal to the number of voxels to be
                integrated at this timestamp. Old tsdf values that need to be
                updated based on the current observation.
            margin_distance (numpy.array [v, ]): The tsdf values of the current observation.
                It should be of type numpy.array [v, ], where v is the number
                of valid voxels.
            w_old (numpy.array [v, ]): old weight values.
            observation_weight (float): Weight to give each new observation.

        Returns:
            numpy.array [v, ]: new tsdf values for entries in tsdf_old
            numpy.array [v, ]: new weights to be used in the future.
        """
        tsdf_new = np.empty_like(tsdf_old, dtype=np.float32)
        w_new = np.empty_like(w_old, dtype=np.float32)

        for i in prange(len(tsdf_old)):
            # TODO:
            w_new[i] = w_old[i] + observation_weight
            tsdf_new[i] = (w_old[i]*tsdf_old[i] + observation_weight*margin_distance[i])/w_new[i]
            #pass
        return tsdf_new, w_new

    def get_valid_points(self, depth_image, voxel_u, voxel_v, voxel_z):
        """ Compute a boolean array for indexing the voxel volume and other variables.
        Note that every time the method integrate(...) is called, not every voxel in
        the volume will be updated. This method returns a boolean matrix called
        valid_points with dimension (n, ), where n = # of voxels. Index i of
        valid_points will be true if this voxel will be updated, false if the voxel
        needs not to be updated.

        The criteria for checking if a voxel is valid or not is shown below.

        Args:
            depth_image (numpy.array [h, w]): A z depth image.
            voxel_u (numpy.array [v, ]): Voxel coordinate projected into image coordinate, axis is u
            voxel_v (numpy.array [v, ]): Voxel coordinate projected into image coordinate, axis is v
            voxel_z (numpy.array [v, ]): Voxel coordinate projected into camera coordinate axis z
        Returns:
            valid_points numpy.array [v, ]: A boolean matrix that will be
            used to index into the voxel grid. Note the dimension of this
            variable.
        """

        image_height, image_width = depth_image.shape

        # TODO 1:
        #  Eliminate pixels not in the image bounds or that are behind the image plane
        # 0 <= voxel_u < image_width and 0 <= voxel_v < image_height

        # TODO 2.1:
        #  Get depths for valid coordinates u, v from the depth image. Zero elsewhere.

        # TODO 2.3:
        #  Filter out zero depth values 

        valid_uv = np.logical_and(voxel_u >= 0,
                  np.logical_and(voxel_u < image_width,
                  np.logical_and(voxel_v >= 0,
                  np.logical_and(voxel_v < image_height,
                  voxel_z > 0))))
        valid_d = np.zeros(voxel_u.shape)
        valid_d[valid_uv] = depth_image[voxel_v[valid_uv], voxel_u[valid_uv]]

        return np.logical_and(valid_d, valid_uv)


    def get_new_colors_with_weights(self, color_old, color_new, w_old, w_new, observation_weight=1.0):
        """ Compute the new RGB values for the color volume given the current values
        in the color volume, the RGB image pixels, and the old and new weights.

        Args:
            color_old (numpy.array [n, 3]): Old colors from self._color_volume in RGB.
            color_new (numpy.array [n, 3]): Newly observed colors from the image in RGB
            w_old (numpy.array [n, ]): Old weights from the self._tsdf_volume
            w_new (numpy.array [n, ]): New weights from calling get_new_tsdf_and_weights
            observation_weight (float, optional):  The weight to assign for the current
                observation. Defaults to 1.
        Returns:
            valid_points numpy.array [n, 3]: The newly computed colors in RGB. Note that
            the input color and output color should have the same dimensions.
        """

        # TODO: Compute the new R, G, and B value by summing the old color
        #  value weighted by the old weight, and the new color weighted by
        #  observation weight. Finally normalize the sum by the new weight.
        #tsdf_new, w_new = self.get_new_tsdf_and_weights(self._tsdf_volume, self._margin_distance, w_old, observation_weight)
        valid_points = np.array(color_old)
        for i in range(len(color_old)):
            valid_points[i][0] = np.minimum(255, np.round((color_old[i][0]*w_old[i] + color_new[i][0]*observation_weight)/w_new[i]))
            valid_points[i][1] = np.minimum(255, np.round((color_old[i][1]*w_old[i] + color_new[i][1]*observation_weight)/w_new[i]))
            valid_points[i][2] = np.minimum(255, np.round((color_old[i][2]*w_old[i] + color_new[i][2]*observation_weight)/w_new[i]))
        
        return valid_points

        #pass

    def integrate(self, color_image, depth_image, camera_intrinsics, camera_pose, observation_weight=1.):
        """Integrate an RGB-D observation into the TSDF volume, by updating the weight volume,
            tsdf volume, and color volume.

        Args:
            color_image (numpy.array [h, w, 3]): An rgb image.
            depth_image (numpy.array [h, w]): A z depth image.
            camera_intrinsics (numpy.array [3, 3]): given as [[fu, 0, u0], [0, fv, v0], [0, 0, 1]]
            camera_pose (numpy.array [4, 4]): SE3 transform representing pose (camera to world)
            observation_weight (float, optional):  The weight to assign for the current
                observation. Defaults to 1.
        """
        color_image = color_image.astype(np.float32)

        # TODO: 1. Project the voxel grid coordinates to the world
        #  space by calling `voxel_to_world`. Then, transform the points
        #  in world coordinate to camera coordinates, which are in (u, v).
        #  You might want to save the voxel z coordinate for later use.
        world_points = self.voxel_to_world(self._volume_origin, self._voxel_coords, self._voxel_size)
        camera_points = transform_point3s(transform_inverse(camera_pose), world_points)
        voxel_z = camera_points[:, 2]
        image_points = camera_to_image(camera_intrinsics, camera_points)
        u = image_points[:, 0]
        v = image_points[:, 1]
 

        # TODO: 2.
        #  Get all of the valid points in the voxel grid by implementing
        #  the helper get_valid_points. Be sure to pass in the correct parameters.
        valid_points = self.get_valid_points(depth_image, u, v, voxel_z)

        # TODO: 3.
        #  With the valid_points array as your indexing array, index into
        #  the self._voxel_coords variable to get the valid voxel x, y, and z.
       
        #x = self._voxel_coords[valid_points, 0]
        #y = self._voxel_coords[valid_points, 1]
        #z = self._voxel_coords[valid_points, 2]

        # TODO: 4. With the valid_points array as your indexing array,
        #  get the valid pixels. Use those valid pixels to index into
        #  the depth_image, and find the valid margin distance.

        valid_d = np.zeros(u.shape)
        valid_d[valid_points] = depth_image[v[valid_points], u[valid_points]]
        diff_depths = valid_d - voxel_z
        #margin_distance = np.minimum(1, diff_depths/self._truncation_margin)
        margin_distance = np.clip(diff_depths/self._truncation_margin, -1, 1)
        margin_distance = margin_distance[valid_points]
        valid_points = np.logical_and(valid_d > 0, diff_depths >= -self._truncation_margin)
        x = self._voxel_coords[valid_points, 0]
        y = self._voxel_coords[valid_points, 1]
        z = self._voxel_coords[valid_points, 2]
        w_old = self._weight_volume[x, y, z]
        tsdf_old = self._tsdf_volume[x, y, z]

        # TODO: 5.
        #  Compute the new weight volume and tsdf volume by calling
        #  `get_new_tsdf_and_weights`. Then update the weight volume
        #  and tsdf volume.
        tsdf_new, w_new = self.get_new_tsdf_and_weights(tsdf_old, margin_distance, w_old, observation_weight)
        self._weight_volume[x, y, z] = w_new
        self._tsdf_volume[x, y, z] = tsdf_new

        # TODO: 6.
        #  Compute the new colors for only the valid voxels by using
        #  get_new_colors_with_weights, and update the current color volume
        #  with the new colors. The color_old and color_new parameters can
        #  be obtained by indexing the valid voxels in the color volume and
        #  indexing the valid pixels in the rgb image.
        color_old = self._color_volume[x, y, z]
        color_new = color_image[v[valid_points], u[valid_points]]
        valid_points = self.get_new_colors_with_weights(color_old, color_new, w_old, w_new, observation_weight=1.0)
        self._color_volume[x, y, z] = valid_points

    """
    *******************************************************************************
    ******************************* ASSIGNMENT ENDS *******************************
    *******************************************************************************
    """
