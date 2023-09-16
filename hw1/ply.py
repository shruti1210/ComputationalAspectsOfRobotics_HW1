import numpy as np
import os


class Ply(object):
    """Class to represent a ply in memory, read plys, and write plys.
    """

    def __init__(self, ply_path=None, triangles=None, points=None, normals=None, colors=None):
        """Initialize the in memory ply representation.

        Args:
            ply_path (str, optional): Path to .ply file to read (note only
                supports text mode, not binary mode). Defaults to None.
            triangles (numpy.array [k, 3], optional): each row is a list of point indices used to
                render triangles. Defaults to None.
            points (numpy.array [n, 3], optional): each row represents a 3D point. Defaults to None.
            normals (numpy.array [n, 3], optional): each row represents the normal vector for the
                corresponding 3D point. Defaults to None.
            colors (numpy.array [n, 3], optional): each row represents the color of the
                corresponding 3D point. Defaults to None.
        """
        super().__init__()
        # TODO: If ply path is None, load in triangles, point, normals, colors.
        #       else load ply from file. If ply_path is specified AND other inputs
        #       are specified as well, ignore other inputs.
        # TODO: If normals are not None make sure that there are equal number of points and normals.
        # TODO: If colors are not None make sure that there are equal number of colors and normals.

        if(ply_path == None):
            self.triangles = triangles
            self.points = points
            self.normals = normals
            self.colors = colors
        else:
            self.read(ply_path)
        #pass

    def write(self, ply_path):
        """Write mesh, point cloud, or oriented point cloud to ply file.

        Args:
            ply_path (str): Output ply path.
        """
        # TODO: Write header depending on existance of normals, colors, and triangles.
        # TODO: Write points.
        # TODO: Write normals if they exist.
        # TODO: Write colors if they exist.
        # TODO: Write face list if needed.
        with open(ply_path, 'w') as f:

            f.write("ply\n")
            f.write("format ascii 1.0\n")
            #(f'element vertex {len(self.points)}\n')
            f.write("element vertex %d\n" % (self.points.shape[0]))
            f.write("property float x\n")
            f.write("property float y\n")
            f.write("property float z\n")
            f.write("property float nx\n")
            f.write("property float ny\n")
            f.write("property float nz\n")
            f.write("property uchar red\n")
            f.write("property uchar green\n")
            f.write("property uchar blue\n")
            if(type(self.triangles) is None):
                f.write("element face %d\n" % (self.triangles.shape[0]))
                f.write("property list uchar int vertex_index\n")
            f.write("end_header\n")
            
            for i in range(self.points.shape[0]):                
                f.write("%f %f %f %f %f %f %d %d %d\n" % (self.points[i, 0], self.points[i, 1], self.points[i, 2], self.normals[i, 0], self.normals[i, 1], self.normals[i, 2], self.colors[i, 0], self.colors[i, 1], self.colors[i, 2],))
            
            if(type(self.triangles) is None):
                for i in range(self.triangles.shape[0]):
                    f.write("3 %d %d %d\n" % (self.triangles[i, 0], self.triangles[i, 1], self.triangles[i, 2]))
        #pass

    def read(self, ply_path):
        """Read a ply into memory.

        Args:
            ply_path (str): ply to read in.
        """
        # TODO: Read in ply.

        with open(ply_path, 'r') as f:
            lines = f.readlines()
        count=0
        for line in lines:
            if line.startswith('ply'):
                count=count+1
                continue
            elif line.startswith('format'):
                count=count+1
                continue
            elif line.startswith('element vertex'):
                num_vertices = int(line.split()[2])
                count=count+1
                continue
            elif line.startswith('property'):
                count=count+1
                continue
            elif line.startswith('element face'):
                num_triangles = int(line.split()[2])
                count=count+1
                continue
            elif line.startswith('end_header'):
                count=count+1
                continue

        points = []
        normals = []
        colors = []
        triangles = []

        for i in range(num_vertices):
            point = lines[count].split()
            points.append([float(point[0]), float(point[1]), float(point[2])])
            normals.append([float(point[3]), float(point[4]), float(point[5])])
            colors.append([int(point[6]), int(point[7]), int(point[8])])
            count=count+1

        self.points = np.asarray(points)
        self.normals = np.asarray(normals)
        self.colors = np.asarray(colors)

        for i in range(num_triangles):
            triangle = lines[count].split()
            triangles.append([int(triangle[1]), int(triangle[2]), int(triangle[3])])
            count = count+1

        self.triangles = np.asarray(triangles)
        
        #pass


#to check the working of the class, uncomment below lines
#ply = Ply()
#ply.read('data/triangle_sample.ply')
#print(ply.points)
#print(ply.normals)
#print(ply.colors)
#print(ply.triangles)
#ply.write('data/triangle_sample_test.ply')
