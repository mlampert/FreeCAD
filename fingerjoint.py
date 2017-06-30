import FreeCAD
import FreeCADGui
import Part
import math
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
        self.dir = (edge.Vertexes[1].Point - edge.Vertexes[0].Point).normalize()

        # there's a possibility this will always be 1.0 ....
        self.scale = (edge.LastParameter - edge.FirstParameter) / edge.Length

        self.normal = face.Surface.Axis
        self.normal.normalize()
        if face.Orientation == 'Reversed':
            self.normal *= -1

        p0 = edge.valueAt(self.scale * (        offset - edge.FirstParameter))
        # the first side of the cutout is along the edge
        p1 = edge.valueAt(self.scale * (dim.x + offset - edge.FirstParameter))
        # second side is in the opposite direction of the normal
        e2 = self.normal * dim.z
        self.e2 = e2

        p2 = p1 - e2
        p3 = p0 - e2

        self.cutPoints = [p0,p1,p2,p3]
        self.cutWire = Part.makePolygon([p0,p1,p2,p3,p0])
        self.cutFace = Part.Face(self.cutWire)

        v = Part.Vertex(self.dir)
        v.rotate(Vector(), self.normal, -90)

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

    def getSelection(self):
        sel = FreeCADGui.Selection.getSelectionEx()
        o0 = sel[0].Object
        self.f00 = sel[0].SubObjects[0]
        o1 = sel[1].Object
        self.f10 = sel[1].SubObjects[0]

        self.f0s = [f for f in o0.Shape.Faces if f.Surface.Axis == self.f00.Surface.Axis]
        self.f1s = [f for f in o1.Shape.Faces if f.Surface.Axis == self.f10.Surface.Axis]
        self.n0s = [f.Surface.Axis if f.Orientation == 'Forward' else f.Surface.Axis * -1 for f in self.f0s]
        self.n1s = [f.Surface.Axis if f.Orientation == 'Forward' else f.Surface.Axis * -1 for f in self.f1s]

        self.f01 = [f for f in o0.Shape.Faces if f.Surface.Axis == self.f00.Surface.Axis and f.Orientation != self.f00.Orientation]
        self.f11 = [f for f in o1.Shape.Faces if f.Surface.Axis == self.f10.Surface.Axis and f.Orientation != self.f10.Orientation]

        self.sections = []
        for f0 in self.f0s:
            for f1 in self.f1s:
                self.sections.append(f0.section(f1))

        return (o0.Shape, self.f00, o1.Shape, self.f10)

    def pointIntoSameDirection(self, p1, p2, tol = 0.001):
        p1.normalize()
        p2.normalize()
        e = p1 - p2
        return math.fabs(e.x) <= tol and math.fabs(e.y) <= tol and math.fabs(e.z) <= tol

    def getEdge(self, solid, face, cutFace):
        section = face.section(cutFace)
        if section.Solids:
            raise Exception("Found solids - there aren't supposed to be any")
        if section.Faces:
            raise Exception("Found faces - there aren't supposed to be any")
        if len(section.Edges) != 1:
            raise Exception("Found %d edges - there is supposed to be exactly 1" % len(section.Edges))
        edge = section.Edges[0]

        n1 = face.Surface.Axis
        n2 = cutFace.Surface.Axis
        nDir = n1.cross(n2)
        eDir = edge.Vertexes[1].Point - edge.Vertexes[0].Point

        if self.pointIntoSameDirection(nDir, eDir):
            return edge
        return Part.Edge(Part.LineSegment(edge.Vertexes[1].Point, edge.Vertexes[0].Point))

    def edgesAreParallel(self, e1, e2, tol=0.0001):
        p10 = e1.Vertexes[0].Point
        p11 = e1.Vertexes[1].Point
        p20 = e2.Vertexes[0].Point
        p21 = e2.Vertexes[1].Point
        d2 = p21 - p20 # there's no point in flipping both edges
        return self.pointIntoSameDirection(p11 - p10, d2) or self.pointIntoSameDirection(p10 - p11, d2)

    def getThickness(self, solid, cutFace, edge):
        common = solid.common(cutFace)
        if len(common.Edges) != 4:
            raise Exception("Found %d edges - expected exactly 1")

        eDir = edge.Vertexes[1].Point - edge.Vertexes[0].Point
        eDir.normalize()
        depths = [e.Length for e in common.Edges if not self.edgesAreParallel(e, edge)]
        return max(depths)

FreeCADGui.doCommand("from FreeCAD import Vector")
FreeCADGui.doCommand("from fingerjoint import Joint, display")

FreeCADGui.doCommand("doc = FreeCAD.newDocument('finger-joint')")

FreeCADGui.doCommand("sheet0 = doc.addObject('Part::Box', 'sheet0')")
sheet0 = FreeCAD.ActiveDocument.sheet0
sheet0.Width  = 200 # 20cm heigh
sheet0.Height =  11 # 3mm thick
sheet0.Length = 300 # 30cm wide
sheet0.ViewObject.Transparency = 80
sheet0.ViewObject.ShapeColor = (random(), random(), random())
FreeCADGui.doCommand("(faceId0,face0) = [f for f in enumerate(sheet0.Shape.Faces) if f[1].Surface.Axis == Vector(0,0,1) and f[1].Orientation != 'Reversed'][0]")

FreeCADGui.doCommand("sheet1 = doc.addObject('Part::Box', 'sheet1')")
sheet1 = FreeCAD.ActiveDocument.sheet1
sheet1.Width  = 200
sheet1.Height = 300
sheet1.Length =   20
sheet1.Placement = FreeCAD.Placement(Vector(sheet0.Length - sheet1.Length,0,0), FreeCAD.Rotation(Vector(0,0,1), 0))
sheet1.ViewObject.Transparency = 80
sheet1.ViewObject.ShapeColor = (random(), random(), random())
FreeCADGui.doCommand("(faceId1,face1) = [f for f in enumerate(sheet1.Shape.Faces) if f[1].Surface.Axis == Vector(1,0,0) and f[1].Orientation == 'Reversed'][0]")

if False:
    FreeCADGui.doCommand("edge = Part.Edge(Part.LineSegment(Vector(297, 0, 3), Vector(297, 200, 3)))")
    FreeCADGui.doCommand("dim0 = FreeCAD.Vector(20, 3, 3)")

    FreeCADGui.doCommand("j0 = Joint()")
    FreeCADGui.doCommand("f0 = j0.featherSolid(sheet0.Shape, face0, edge, dim0, 10)")
    FreeCADGui.doCommand("display(f0, 'feather0')")

    FreeCAD.ActiveDocument.feather0.ViewObject.ShapeColor = sheet0.ViewObject.ShapeColor
    FreeCAD.ActiveDocument.feather0.ViewObject.Transparency = 80

    FreeCADGui.doCommand("dim1 = FreeCAD.Vector(20, -3, 3)")

    FreeCADGui.doCommand("j1 = Joint()")
    FreeCADGui.doCommand("f1 = j1.featherSolid(sheet1.Shape, face1, edge, dim1, -10)")
    FreeCADGui.doCommand("display(f1, 'feather1')")

    FreeCAD.ActiveDocument.feather1.ViewObject.ShapeColor = sheet1.ViewObject.ShapeColor
    FreeCAD.ActiveDocument.feather1.ViewObject.Transparency = 80

    sheet0.ViewObject.Visibility = False
    sheet1.ViewObject.Visibility = False

else:
    FreeCADGui.Selection.clearSelection()
    # Let's select the 2 outside edges, that do not intersect at all
    FreeCADGui.doCommand("(faceId0,face0) = [f for f in enumerate(sheet0.Shape.Faces) if f[1].Surface.Axis == Vector(0,0,1) and f[1].Orientation == 'Reversed'][0]")
    FreeCADGui.doCommand("(faceId1,face1) = [f for f in enumerate(sheet1.Shape.Faces) if f[1].Surface.Axis == Vector(1,0,0) and f[1].Orientation != 'Reversed'][0]")
    FreeCADGui.doCommand("Gui.Selection.addSelection(sheet0, 'Face%d' % (faceId0+1))")
    FreeCADGui.doCommand("Gui.Selection.addSelection(sheet1, 'Face%d' % (faceId1+1))")

    FreeCADGui.doCommand("j = Joint()")
    FreeCADGui.doCommand("(s0, f0, s1, f1)  = j.getSelection()")
    FreeCADGui.doCommand("e0 = j.getEdge(s0, f0, f1)")
    FreeCADGui.doCommand("e1 = j.getEdge(s1, f1, f0)")
    FreeCADGui.doCommand("d0 = j.getThickness(s0, f1, e0)")
    FreeCADGui.doCommand("d1 = j.getThickness(s1, f0, e1)")

    FreeCADGui.doCommand("f0 = j.featherSolid(s0, f0, e0, Vector(20, d1, d0),  10)")
    FreeCADGui.doCommand("display(f0, 'feather0')")

    FreeCADGui.doCommand("f1 = j.featherSolid(s1, f1, e1, Vector(20, d0, d1), -10)")
    FreeCADGui.doCommand("display(f1, 'feather1')")

    FreeCAD.ActiveDocument.feather0.ViewObject.ShapeColor = sheet0.ViewObject.ShapeColor
    FreeCAD.ActiveDocument.feather0.ViewObject.Transparency = 80
    FreeCAD.ActiveDocument.feather1.ViewObject.ShapeColor = sheet1.ViewObject.ShapeColor
    FreeCAD.ActiveDocument.feather1.ViewObject.Transparency = 80

    sheet0.ViewObject.Visibility = False
    sheet1.ViewObject.Visibility = False

FreeCADGui.ActiveDocument.ActiveView.fitAll()
FreeCADGui.ActiveDocument.ActiveView.viewAxonometric()
FreeCAD.ActiveDocument.recompute()
