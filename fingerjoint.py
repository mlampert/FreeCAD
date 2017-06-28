import FreeCAD
import FreeCADGui
import Part

from FreeCAD import Vector

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
          edge   ... an edge on the solid along which to feather
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

        p0 = edge.valueAt(self.scale * (offset - edge.FirstParameter))
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
FreeCADGui.doCommand("sheet = doc.addObject('Part::Box', 'sheet')")

FreeCADGui.doCommand("sheet.Width  = 200 # 20cm heigh")
FreeCADGui.doCommand("sheet.Height =   3 # 3mm thick")
FreeCADGui.doCommand("sheet.Length = 300 # 30cm wide")
FreeCADGui.doCommand("sheet.ViewObject.Transparency = 80")

FreeCADGui.doCommand("(faceId,face) = [f for f in enumerate(sheet.Shape.Faces) if f[1].Surface.Axis == Vector(0,0,1) and f[1].Orientation == 'Reversed'][0]")
FreeCADGui.doCommand("edge = Part.Edge(Part.LineSegment(Vector(290, 0, 3), Vector(290, 200, 3)))")
FreeCADGui.doCommand("dim = FreeCAD.Vector(20, 10, 3)")

FreeCADGui.doCommand("j = Joint()")
FreeCADGui.doCommand("f = j.featherSolid(sheet.Shape, face, edge, dim, offset=10)")
FreeCADGui.doCommand("display(f, 'feather')")

FreeCADGui.ActiveDocument.ActiveView.fitAll()
FreeCADGui.ActiveDocument.ActiveView.viewAxonometric()
FreeCAD.ActiveDocument.recompute()
