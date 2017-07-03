import FreeCAD
import Part
import math

from PySide import QtCore

if FreeCAD.GuiUp:
    import FreeCADGui
    from PySide import QtGui

def getBodyFor(obj):
    for o in obj.InList:
        if hasattr(o, 'Group') and hasattr(o, 'Tip'):
            return o
    return None

def getShapeFor(obj):
    shape = obj.Shape.copy()

    body = getBodyFor(obj)
    if body:
        shape.transformShape(body.Shape.Matrix)
    return shape

def getNormal(face):
    normal = face.Surface.Axis
    normal.normalize()
    if face.Orientation == 'Reversed':
        normal *= -1
    return normal

class Joint:

    def __init__(self, obj, base, face, joiner):
        obj.addProperty('App::PropertyLinkSub',  'Face',       'Joint', QtCore.QT_TRANSLATE_NOOP('PartDesign_FingerJoint', 'The object coordinating the joint.'))
        obj.addProperty('App::PropertyLink',     'Joiner',     'Joint', QtCore.QT_TRANSLATE_NOOP('PartDesign_FingerJoint', 'The object coordinating the joint.'))
        obj.addProperty('App::PropertyDistance', 'ExtraWidth', 'Joint', QtCore.QT_TRANSLATE_NOOP('PartDesign_FingerJoint', 'Extra width applied to joint cut.'))
        obj.Proxy = self

        obj.Face     = (base, face)
        obj.Joiner   = joiner

    def getBody(self, obj):
        return getBodyFor(obj)

    def getMatrix(self, obj):
        return self.getBody(obj).Shape.Matrix

    def getBaseObject(self, obj):
        return obj.Face[0]

    def getBaseShape(self, obj):
        return getShapeFor(self.getBaseObject(obj))

    def getBaseFace(self, obj):
        face = self.getBaseObject(obj).Shape.getElement(obj.Face[1][0])
        face.transformShape(self.getMatrix(obj))
        return face

    def execute(self, obj):
        if not hasattr(obj, 'Joiner'):
            return None

        self.name   = obj.Name
        self.joiner = obj.Joiner.Proxy
        self.solid  = self.joiner.jointShapeFor(obj)
        self.face   = self.joiner.jointFaceFor(obj)
        self.edge   = self.joiner.jointEdgeFor(obj)
        self.dim    = self.joiner.jointDimensionsFor(obj)
        self.offset = self.joiner.jointOffsetFor(obj)
        # need to convert world coordinates into body coordinates
        self.matrix = self.getMatrix(obj).inverse()

        self.shape  = self.featherSolid(self.solid, self.face, self.edge, self.dim, self.offset)

        #self.shape.transformShape(self.matrix)
        obj.Shape = self.shape
        obj.Placement = self.getBody(obj).Placement.inverse()

    def featherSolid(self, solid, face, edge, dim, offset=0):
        '''
        featherSolid(solid, face, edge, dim, offst=0) .... create finger joint feathers,
          solid  ... the solid to feature
          face   ... a face on the solid
          edge   ... an edge on the face along which to feather
          dim    ... vector of feather dimensions Vector(length, width, depth)
          offset ... offset from the edge's starting point to the first feather cut
        '''

        #self.solid = solid
        #self.face = face
        #self.edge = edge
        #self.dim = dim
        #self.offset = offset
        self.start = edge.Vertexes[0].Point
        self.dir = (edge.Vertexes[1].Point - edge.Vertexes[0].Point).normalize()
        print("%s.dir = [%.2f, %.2f, %.2f]" % (self.name, self.dir.x, self.dir.y, self.dir.z))

        # there's a possibility this will always be 1.0 ....
        self.scale = (edge.LastParameter - edge.FirstParameter) / edge.Length

        self.normal = getNormal(face)
        print("%s.nrm = [%.2f, %.2f, %.2f] flipped=%d" % (self.name, self.normal.x, self.normal.y, self.normal.z, face.Orientation == 'Reversed'))

        diff = self.dir * (self.scale * self.dim.x)

        p0 = self.start + self.dir * (self.scale * self.offset)
        # the first side of the cutout is along the edge
        p1 = p0 + diff
        # second side is in the opposite direction of the normal
        e2 = self.normal * dim.z
        self.e2 = e2

        p2 = p1 - e2
        p3 = p0 - e2

        self.cutPoints = [p0,p1,p2,p3]
        self.cutWire = Part.makePolygon([p0,p1,p2,p3,p0])
        self.cutFace = Part.Face(self.cutWire)

        v = Part.Vertex(self.dir)
        v.rotate(FreeCAD.Vector(), self.normal, -90)

        self.cutSolid = self.cutFace.extrude(v.Point * dim.y)

        trans = FreeCAD.Vector(0,0,0)
        self.cut = []

        while offset < edge.Length:
            cut = self.cutSolid.copy()
            cut.translate(trans)
            self.cut.append(cut)
            trans  += 2 * diff
            offset += 2 * dim.x

        self.cutOuts = Part.makeCompound(self.cut)
        return solid.cut(self.cutOuts)

class FingerJoiner:
    def __init__(self, obj, base, tool):
        obj.addProperty('App::PropertyLink',     'Base',        'Joint',  QtCore.QT_TRANSLATE_NOOP('PartDesign_FingerJoint', 'One body to add joint to'))
        obj.addProperty('App::PropertyLink',     'Tool',        'Joint',  QtCore.QT_TRANSLATE_NOOP('PartDesign_FingerJoint', 'Another body to add joint to'))
        obj.addProperty('App::PropertyDistance', 'Size',        'Finger', QtCore.QT_TRANSLATE_NOOP('PartDesign_FingerJoint', 'Extra width applied to joint cut.'))
        obj.addProperty('App::PropertyDistance', 'Offset',      'Finger', QtCore.QT_TRANSLATE_NOOP('PartDesign_FingerJoint', 'Extra width applied to joint cut.'))
        obj.addProperty('App::PropertyDistance', 'ExtraLength', 'Finger', QtCore.QT_TRANSLATE_NOOP('PartDesign_FingerJoint', 'Extra width applied to joint cut.'))
        obj.addProperty('App::PropertyDistance', 'ExtraWidth',  'Finger', QtCore.QT_TRANSLATE_NOOP('PartDesign_FingerJoint', 'Extra width applied to joint cut.'))
        obj.addProperty('App::PropertyDistance', 'ExtraDepth',  'Finger', QtCore.QT_TRANSLATE_NOOP('PartDesign_FingerJoint', 'Extra width applied to joint cut.'))

        obj.Proxy = self
        obj.Base  = base
        obj.Tool  = tool

        obj.setEditorMode('Base', 1) # ro
        obj.setEditorMode('Tool', 1) # ro

        obj.Size = 20

    def execute(self, obj):
        print('')
        self.joints = [o for o in obj.InList if hasattr(o, 'Proxy') and hasattr(o, 'Joiner')]
        self.jointBase = next(j for j in self.joints if j.Proxy.getBaseObject(j).Name == obj.Base.Name)
        self.jointTool = next(j for j in self.joints if j.Proxy.getBaseObject(j).Name == obj.Tool.Name)
        self.base = self.jointBase.Proxy
        self.tool = self.jointTool.Proxy

        self.shapeBase = self.base.getBaseShape(self.jointBase)
        self.shapeTool = self.tool.getBaseShape(self.jointTool)

        self.faceBase = self.base.getBaseFace(self.jointBase)
        self.faceTool = self.tool.getBaseFace(self.jointTool)

        (self.flipBase, self.edgeBase) = self.getEdge(self.shapeBase, self.faceBase, self.faceTool, 'base')
        (self.flipTool, self.edgeTool) = self.getEdge(self.shapeTool, self.faceTool, self.faceBase, 'tool')

        self.dimBase = self.getThickness(self.shapeBase, self.faceTool, self.edgeBase)
        self.dimTool = self.getThickness(self.shapeTool, self.faceBase, self.edgeTool)

        self.length = obj.Size.Value
        self.offsetBase = obj.Offset.Value
        self.offsetTool = self.offsetBase + self.length

        self.cutShape = self.shapeBase.common(self.shapeTool)
        obj.Shape = self.cutShape

    def jointShapeFor(self, joint):
        if joint == self.jointBase:
            return self.shapeBase
        return self.shapeTool

    def jointFaceFor(self, joint):
        if joint == self.jointBase:
            return self.faceBase
        return self.faceTool

    def jointEdgeFor(self, joint):
        # both bodies should operate on the same edge for proper offset processing
        return self.edgeBase

    def jointDimensionsFor(self, joint):
        if joint == self.jointBase:
            return FreeCAD.Vector(self.length, -self.dimTool, self.dimBase)
        return FreeCAD.Vector(self.length,  self.dimBase, self.dimTool)

    def jointOffsetFor(self, joint):
        if joint == self.jointBase:
            return self.offsetBase
        return self.offsetTool

    def pointIntoSameDirection(self, p1, p2, tol = 0.001):
        p1.normalize()
        p2.normalize()
        e = p1 - p2
        return math.fabs(e.x) <= tol and math.fabs(e.y) <= tol and math.fabs(e.z) <= tol

    def getEdge(self, solid, face, cutFace, name):
        section = face.section(cutFace)
        if section.Solids:
            raise Exception("Found solids - there aren't supposed to be any")
        if section.Faces:
            raise Exception("Found faces - there aren't supposed to be any")
        if len(section.Edges) != 1:
            raise Exception("Found %d edges - there is supposed to be exactly 1" % len(section.Edges))
        edge = section.Edges[0]

        n1 = getNormal(face)
        n2 = getNormal(cutFace)
        nDir = n1.cross(n2)
        eDir = edge.Vertexes[1].Point - edge.Vertexes[0].Point

        if self.pointIntoSameDirection(nDir, eDir):
            print("%s: edge" % name)
            return (False, edge)
        print("%s: flipped edge" % name)
        return (True, Part.Edge(Part.LineSegment(edge.Vertexes[1].Point, edge.Vertexes[0].Point)))

    def edgesAreParallel(self, e1, e2, tol=0.0001):
        p10 = e1.Vertexes[0].Point
        p11 = e1.Vertexes[1].Point
        p20 = e2.Vertexes[0].Point
        p21 = e2.Vertexes[1].Point
        d2 = p21 - p20 # there's no point in flipping both edges
        return self.pointIntoSameDirection(p11 - p10, d2) or self.pointIntoSameDirection(p10 - p11, d2)

    def getThickness(self, solid, cutFace, edge):
        common = solid.common(cutFace)
        #if len(common.Edges) != 4:
        #    raise Exception("Found %d edges - expected exactly 1" % len(common.Edges))

        eDir = edge.Vertexes[1].Point - edge.Vertexes[0].Point
        eDir.normalize()
        depths = [e.Length for e in common.Edges if not self.edgesAreParallel(e, edge)]
        return max(depths)

class ViewProviderFingerJoint:
    def __init__(self, vobj):
        vobj.Proxy = self
        self.vobj = vobj
        self.obj = vobj.Object

    def attach(self, vobj):
        self.Object = vobj.Object

    def getIcon(self):
        return ':/icons/PartDesign_FingerJoint.svg'

    def onChanged(self, vobj, prop):
        print("finger-joint: %s" % prop)

    def __getstate__(self):
        return None
    def __setstate__(self):
        return None

class ViewProviderJoint:
    def __init__(self, vobj):
        vobj.Proxy = self
        self.vobj = vobj

    def attach(self, vobj):
        self.vobj = vobj
        self.Object = vobj.Object

        baseVobj = vobj.Object.BaseFeature.ViewObject
        baseVobj.Visibility = False
        vobj.DiffuseColor = baseVobj.DiffuseColor
        vobj.Transparency = baseVobj.Transparency

    def getIcon(self):
        return ':/icons/PartDesign_FingerJoint.svg'

    def onChanged(self, vobj, prop):
        print("joint: %s" % prop)

    def __getstate__(self):
        return None
    def __setstate__(self):
        return None

def Create(name):
    def createJoint(obj, face, joiner):
        for o in obj.InList:
            if hasattr(o, 'Group') and hasattr(o, 'Tip'):
                # PartDesign
                joint = FreeCAD.ActiveDocument.addObject('PartDesign::FeaturePython', 'Joint')
                proxy = Joint(joint, obj, face, joiner)
                o.addObject(joint)
                return (joint, proxy)
        # All other objects
        joint = FreeCAD.ActiveDocument.addObject('Part::FeaturePython', 'Joint')
        proxy = Joint(joint, obj, face, joiner)
        o.addObject(joint)
        return (joint, proxy)

    sel = FreeCADGui.Selection.getSelectionEx()
    if len(sel) == 2 and len(sel[0].SubObjects) == 1 and len(sel[1].SubObjects) == 1:
        joiner = FreeCAD.ActiveDocument.addObject('Part::FeaturePython', name)
        finger = FingerJoiner(joiner, sel[0].Object, sel[1].Object)

        (o0, p0) = createJoint(sel[0].Object, sel[0].SubElementNames[0], joiner)
        (o1, p1) = createJoint(sel[1].Object, sel[1].SubElementNames[0], joiner)

        if FreeCAD.GuiUp:
            ViewProviderFingerJoint(joiner.ViewObject)
            joiner.ViewObject.Visibility = False
            ViewProviderJoint(o0.ViewObject)
            ViewProviderJoint(o1.ViewObject)

        return joiner

    else:
        return None


class Command:
    def GetResources(self):
        return {'Pixmap'  : 'PartDesign_FingerJoint',
                'MenuText': QtCore.QT_TRANSLATE_NOOP("PartDesign_FingerJoint","Finger Joint"),
                'Accel': "",
                'ToolTip': QtCore.QT_TRANSLATE_NOOP("PartDesign_FingerJoint","Creates matching finger joints in two intersecting bodies.")}
        
    def Activated(self):
        FreeCAD.ActiveDocument.openTransaction("Create matching finger joint cuts")
        FreeCADGui.addModule("FingerJoint")
        FreeCADGui.doCommand("FingerJoint.Create('FingerJoint')")
        FreeCAD.ActiveDocument.recompute()
        FreeCAD.ActiveDocument.commitTransaction()
        #FreeCADGui.doCommand("Gui.activeDocument().setEdit(App.ActiveDocument.ActiveObject.Name,0)")
        
    def IsActive(self):
        return len(FreeCADGui.Selection.getSelection()) == 2

if FreeCAD.GuiUp:
    FreeCADGui.addCommand('PartDesign_FingerJoint',Command())
