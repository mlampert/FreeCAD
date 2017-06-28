import FreeCAD
import FreeCADGui
import Part
import random

from FreeCAD import Vector
from random import random

def display(shape, name):
    part = FreeCAD.ActiveDocument.addObject('Part::Feature', name)
    part.Shape = shape
    FreeCAD.ActiveDocument.recompute()

class Joint:
    def featherSolid(self, solid, face, edge, dim, offset=0):
        '''
        featherSolid(solid, face, edge, dim, offst=0) .... create finger joint feathers,
          solid  ... the solid to feature
          face   ... a face on the solid
          edge   ... an edge on the face along which to feather
          dim    ... vector of feather dimensions Vector(length, width, depth)
          offset ... offset from the edge's starting point to the first feather cut
        '''

        self.solid = solid
        self.face = face
        self.edge = edge
        self.dim = dim
        self.offset = offset
        self.start = edge.Vertexes[0].Point
        self.dir = edge.Vertexes[1].Point - edge.Vertexes[0].Point

        # there's a possibility this will always be 1.0 ....
        self.scale = (edge.LastParameter - edge.FirstParameter) / edge.Length

        self.normal = face.Surface.Axis
        self.normal.normalize()
        if face.Orientation == 'Reversed':
            self.normal *= -1

        p0 = edge.valueAt(self.scale * (        offset - edge.FirstParameter))
        # the first side of the cutout is along the edge
        p1 = edge.valueAt(self.scale * (dim.x + offset - edge.FirstParameter))
        # scond side is in the direction of the normal
        e2 = self.normal * dim.z

        p2 = p1 + e2
        p3 = p0 + e2

        self.cutPoints = [p0,p1,p2,p3]
        self.cutWire = Part.makePolygon([p0,p1,p2,p3,p0])
        self.cutFace = Part.Face(self.cutWire)

        v = Part.Vertex(self.normal)
        v.rotate(Vector(), self.dir, -90)

        self.cutSolid = self.cutFace.extrude(v.Point * dim.y)

        diff = p1 - p0
        trans = Vector(0,0,0)
        self.cut = []

        while offset < edge.Length:
            cut = self.cutSolid.copy()
            cut.translate(trans)
            self.cut.append(cut)
            trans  += 2 * diff
            offset += 2 * dim.x

        self.cutOuts = Part.makeCompound(self.cut)
        return solid.cut(self.cutOuts)

    def makeBox(self, x, y, z):
        s = Part.makeBox(20, 10, 1, Vector(0,0,0), Vector(x,y,z))
        display(s, "box-%d%d%d" % (x,y,z))

FreeCADGui.doCommand("from FreeCAD import Vector")
FreeCADGui.doCommand("from fingerjoint import Joint, display")

FreeCADGui.doCommand("doc = FreeCAD.newDocument('finger-joint')")

FreeCADGui.doCommand("sheet0 = doc.addObject('Part::Box', 'sheet0')")
FreeCADGui.doCommand("sheet0.Width  = 200 # 20cm heigh")
FreeCADGui.doCommand("sheet0.Height =   3 # 3mm thick")
FreeCADGui.doCommand("sheet0.Length = 300 # 30cm wide")
FreeCADGui.doCommand("sheet0.ViewObject.Transparency = 80")
FreeCADGui.doCommand("sheet0.ViewObject.Visibility = False")

FreeCADGui.doCommand("edge = Part.Edge(Part.LineSegment(Vector(297, 0, 3), Vector(297, 200, 3)))")
FreeCADGui.doCommand("dim0 = FreeCAD.Vector(20, 3, 3)")

FreeCADGui.doCommand("(faceId0,face0) = [f for f in enumerate(sheet0.Shape.Faces) if f[1].Surface.Axis == Vector(0,0,1) and f[1].Orientation == 'Reversed'][0]")
FreeCADGui.doCommand("j0 = Joint()")
FreeCADGui.doCommand("f0 = j0.featherSolid(sheet0.Shape, face0, edge, dim0, offset=10)")
FreeCADGui.doCommand("display(f0, 'feather0')")


FreeCADGui.doCommand("sheet1 = doc.addObject('Part::Box', 'sheet1')")
FreeCADGui.doCommand("sheet1.Width  = 200")
FreeCADGui.doCommand("sheet1.Height = 300")
FreeCADGui.doCommand("sheet1.Length =   3")
FreeCADGui.doCommand("sheet1.Placement = FreeCAD.Placement(Vector(297,0,0), FreeCAD.Rotation(Vector(0,0,1), 0))")
FreeCADGui.doCommand("sheet1.ViewObject.Transparency = 80")
FreeCADGui.doCommand("sheet1.ViewObject.Visibility = False")

FreeCADGui.doCommand("dim1 = FreeCAD.Vector(20, -3, 3)")

FreeCADGui.doCommand("(faceId1,face1) = [f for f in enumerate(sheet0.Shape.Faces) if f[1].Surface.Axis == Vector(1,0,0) and f[1].Orientation != 'Reversed'][0]")
FreeCADGui.doCommand("j1 = Joint()")
FreeCADGui.doCommand("f1 = j1.featherSolid(sheet1.Shape, face1, edge, dim1, offset=-10)")
FreeCADGui.doCommand("display(f1, 'feather1')")

FreeCAD.ActiveDocument.sheet0.ViewObject.ShapeColor = (random(), random(), random())
FreeCAD.ActiveDocument.feather0.ViewObject.ShapeColor = FreeCAD.ActiveDocument.sheet0.ViewObject.ShapeColor
FreeCAD.ActiveDocument.feather0.ViewObject.Transparency = 80
FreeCAD.ActiveDocument.sheet1.ViewObject.ShapeColor = (random(), random(), random())
FreeCAD.ActiveDocument.feather1.ViewObject.ShapeColor = FreeCAD.ActiveDocument.sheet1.ViewObject.ShapeColor
FreeCAD.ActiveDocument.feather1.ViewObject.Transparency = 80

FreeCADGui.ActiveDocument.ActiveView.fitAll()
FreeCADGui.ActiveDocument.ActiveView.viewAxonometric()
FreeCAD.ActiveDocument.recompute()
