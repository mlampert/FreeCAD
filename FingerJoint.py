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
        obj.addProperty('App::PropertyLinkSub',  'Face',       'Joint', QtCore.QT_TRANSLATE_NOOP('FingerJoint', 'The object coordinating the joint.'))
        obj.addProperty('App::PropertyLink',     'Joiner',     'Joint', QtCore.QT_TRANSLATE_NOOP('FingerJoint', 'The object coordinating the joint.'))
        obj.addProperty('App::PropertyDistance', 'ExtraWidth', 'Joint', QtCore.QT_TRANSLATE_NOOP('FingerJoint', 'Extra width applied to joint cut.'))
        obj.Proxy = self

        obj.Face     = (base, face)
        obj.Joiner   = joiner

    def __getstate__(self):
        return None
    def __setstate__(self, state):
        return None

    def isPartDesignFeature(self, obj):
        return hasattr(obj.Face[0], 'BaseFeature')

    def getBody(self, obj):
        if self.isPartDesignFeature(obj):
            return getBodyFor(obj)
        return obj

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
        if self.joiner.jointIsValidFor(obj):
            self.solid  = self.joiner.jointShapeFor(obj)
            self.face   = self.joiner.jointFaceFor(obj)
            self.edge   = self.joiner.jointEdgeFor(obj)
            self.dim    = self.joiner.jointDimensionsFor(obj)
            self.offset = self.joiner.jointOffsetFor(obj)
            self.slack  = self.joiner.jointSlackFor(obj)
            self.shape  = self.featherSolid(self.solid, self.face, self.edge, self.dim, self.offset, self.slack, obj.ExtraWidth.Value)
            obj.Shape   = self.shape
            obj.Placement = self.getBody(obj).Placement.inverse()
        else:
            obj.Shape = self.getBaseShape(obj)
            obj.Placement = self.getBaseObject(obj).Placement

    def featherSolid(self, solid, face, edge, dim, offset=0, slack = FreeCAD.Vector(0,0,0), extend=0):
        '''
        featherSolid(solid, face, edge, dim, offst=0) .... create finger joint feathers,
          solid  ... the solid to feature
          face   ... a face on the solid
          edge   ... an edge on the face along which to feather
          dim    ... vector of feather dimensions Vector(length, width, depth)
          offset ... offset from the edge's starting point to the first feather cut
          slack  ... vector of extra material to be removed in each direction (length, width, depth)
          extend ... extend the width of the finger in one direction by given amount
                     positive values are in finger direction, negative values in opposite direction
        '''

        #self.solid = solid
        #self.face = face
        #self.edge = edge
        #self.dim = dim
        #self.offset = offset
        self.start = edge.Vertexes[0].Point
        self.dir = (edge.Vertexes[1].Point - edge.Vertexes[0].Point).normalize()

        # there's a possibility this will always be 1.0 ....
        self.scale = (edge.LastParameter - edge.FirstParameter) / edge.Length

        self.normal = getNormal(face)

        diff = self.dir * (self.scale * self.dim.x)

        p0 = self.start + self.dir * (self.scale * (self.offset - slack.x))
        # the first side of the cutout is along the edge
        p1 = p0 + diff + self.dir * (self.scale * 2 * slack.x)
        # second side is in the opposite direction of the normal
        e2 = self.normal * (dim.z + slack.z)
        self.e2 = e2

        p2 = p1 - e2
        p3 = p0 - e2

        self.cutPoints = [p0,p1,p2,p3]
        self.cutWire = Part.makePolygon([p0,p1,p2,p3,p0])
        self.cutFace = Part.Face(self.cutWire)

        v = Part.Vertex(self.dir)
        v.rotate(FreeCAD.Vector(), self.normal, -90)

        width = dim.y + slack.y
        if extend > 0:
            if width > 0:
                width += extend
            else:
                width -= extend
        self.cutSolid = self.cutFace.extrude(v.Point * self.scale * width)

        if math.fabs(slack.y) > 0.000001 or extend < 0:
            if width < 0:
                width = slack.y + extend
            else:
                width = slack.y - extend
            self.cutFinger = self.cutSolid
            self.cutSlack = self.cutFace.extrude(v.Point * -1 * self.scale * width)
            self.cutSolid = self.cutSolid.fuse(self.cutSlack)

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
        obj.addProperty('App::PropertyString',   'BaseJoint',   'Joint',  QtCore.QT_TRANSLATE_NOOP('FingerJoint', 'One body to add joint to'))
        obj.addProperty('App::PropertyString',   'ToolJoint',   'Joint',  QtCore.QT_TRANSLATE_NOOP('FingerJoint', 'Another body to add joint to'))
        obj.addProperty('App::PropertyDistance', 'Size',        'Finger', QtCore.QT_TRANSLATE_NOOP('FingerJoint', 'Extra width applied to joint cut.'))
        obj.addProperty('App::PropertyDistance', 'Offset',      'Finger', QtCore.QT_TRANSLATE_NOOP('FingerJoint', 'Extra width applied to joint cut.'))
        obj.addProperty('App::PropertyDistance', 'ExtraLength', 'Finger', QtCore.QT_TRANSLATE_NOOP('FingerJoint', 'Extra width applied to joint cut.'))
        obj.addProperty('App::PropertyDistance', 'ExtraWidth',  'Finger', QtCore.QT_TRANSLATE_NOOP('FingerJoint', 'Extra width applied to joint cut.'))
        obj.addProperty('App::PropertyDistance', 'ExtraDepth',  'Finger', QtCore.QT_TRANSLATE_NOOP('FingerJoint', 'Extra width applied to joint cut.'))

        obj.Proxy = self
        obj.BaseJoint = base.Name
        obj.ToolJoint = tool.Name

        obj.setEditorMode('BaseJoint', 1) # ro
        obj.setEditorMode('ToolJoint', 1) # ro
        obj.setEditorMode('Placement', 2) # hide

        obj.Size = 100

    def __getstate__(self):
        return None
    def __setstate__(self, state):
        return None

    def execute(self, obj):
        print("%s(%s, %s)" % (obj.Name, obj.BaseJoint, obj.ToolJoint))
        self.jointBase = obj.Document.getObject(obj.BaseJoint)
        self.jointTool = obj.Document.getObject(obj.ToolJoint)
        self.base = self.jointBase.Proxy
        self.tool = self.jointTool.Proxy

        self.shapeBase = self.base.getBaseShape(self.jointBase)
        self.shapeTool = self.tool.getBaseShape(self.jointTool)

        self.faceBase = self.base.getBaseFace(self.jointBase)
        self.faceTool = self.tool.getBaseFace(self.jointTool)

        (self.flipBase, self.edgeBase) = self.getEdge(self.shapeBase, self.faceBase, self.faceTool)
        (self.flipTool, self.edgeTool) = self.getEdge(self.shapeTool, self.faceTool, self.faceBase)

        if self.edgeBase and self.edgeTool:
            self.dimBase = self.getThickness(self.shapeBase, self.faceTool, self.edgeBase)
            self.dimTool = self.getThickness(self.shapeTool, self.faceBase, self.edgeTool)

            self.length = obj.Size.Value
            self.offsetBase = obj.Offset.Value
            self.offsetTool = self.offsetBase + self.length

            self.extraLength = obj.ExtraLength.Value
            self.extraWidth  = obj.ExtraWidth.Value
            self.extraDepth  = obj.ExtraDepth.Value
        else:
            self.dimBase = 0
            self.dimTool = 0

        self.cutShape = self.shapeBase.common(self.shapeTool)
        obj.Shape = self.cutShape

    def jointIsValidFor(self, joint):
        return hasattr(self, 'dimBase') and hasattr(self, 'dimTool') and self.dimBase != 0 and self.dimTool != 0

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

    def jointSlackFor(self, joint):
        if joint == self.jointBase:
            return FreeCAD.Vector(self.extraLength, -self.extraWidth, self.extraDepth)
        return FreeCAD.Vector(self.extraLength, self.extraWidth, self.extraDepth)

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
        if len(section.Edges) == 0:
            #raise Exception("Found %d edges - there is supposed to be exactly 1" % len(section.Edges))
            return (False, None)
        if len(section.Edges) == 1:
            edge = section.Edges[0]
        else:
            # this can happen if the edge is interrupted by pockets, most likely from
            # another FingerJoint operation
            self.rogueEdges = section.Edges
            curve = section.Edges[0].Curve
            pts = [v.Point for e in section.Edges for v in e.Vertexes]
            params = [curve.parameter(p) for p in pts]
            minParam = min(params)
            maxParam = max(params)
            begin = curve.value(minParam)
            end   = curve.value(maxParam)
            edge = Part.Edge(Part.LineSegment(begin, end))

        n1 = getNormal(face)
        n2 = getNormal(cutFace)
        nDir = n1.cross(n2)
        eDir = edge.Vertexes[1].Point - edge.Vertexes[0].Point

        if self.pointIntoSameDirection(nDir, eDir):
            return (False, edge)
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
        if depths:
            return max(depths)
        return 0

class ViewProviderFingerJoint:
    def __init__(self, vobj):
        vobj.Proxy = self
        self.vobj = vobj
        self.obj = vobj.Object

    def attach(self, vobj):
        self.Object = vobj.Object

    #def getIcon(self):
    #    return ':/icons/FingerJoint.svg'

    def __getstate__(self):
        return None
    def __setstate__(self, state):
        return None

class ViewProviderJoint:
    def __init__(self, vobj):
        vobj.Proxy = self
        self.vobj = vobj

    def forPartDesign(self):
        return hasattr(self.Object, 'BaseFeature')

    def attach(self, vobj):
        self.vobj = vobj
        self.Object = vobj.Object

        baseVobj = self.Object.BaseFeature.ViewObject if self.forPartDesign() else self.Object.Face[0].ViewObject
        baseVobj.Visibility = False
        vobj.DiffuseColor = baseVobj.DiffuseColor
        vobj.Transparency = baseVobj.Transparency

    def claimChildren(self):
        if self.forPartDesign():
            return []
        return [self.Object.Face[0]]

    #def getIcon(self):
    #    return ':/icons/FingerJoint.svg'

    def __getstate__(self):
        return None
    def __setstate__(self, state):
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
        return (joint, proxy)

    sel = FreeCADGui.Selection.getSelectionEx()
    if len(sel) == 2 and len(sel[0].SubObjects) == 1 and len(sel[1].SubObjects) == 1:
        FreeCAD.ActiveDocument.openTransaction("Create matching finger joint cuts")
        joiner = FreeCAD.ActiveDocument.addObject('Part::FeaturePython', name)

        (o0, p0) = createJoint(sel[0].Object, sel[0].SubElementNames[0], joiner)
        (o1, p1) = createJoint(sel[1].Object, sel[1].SubElementNames[0], joiner)

        finger = FingerJoiner(joiner, o0, o1)

        if FreeCAD.GuiUp:
            ViewProviderFingerJoint(joiner.ViewObject)
            joiner.ViewObject.Visibility = False
            ViewProviderJoint(o0.ViewObject)
            ViewProviderJoint(o1.ViewObject)

        FreeCAD.ActiveDocument.recompute()
        FreeCAD.ActiveDocument.commitTransaction()
        return joiner

    else:
        return None


class Command:
    def GetResources(self):
        return {'Pixmap'  : 'FingerJoint.svg',
                'MenuText': QtCore.QT_TRANSLATE_NOOP("FingerJoint","Finger Joint"),
                'Accel': "",
                'ToolTip': QtCore.QT_TRANSLATE_NOOP("FingerJoint","Creates matching finger joints in two intersecting bodies.")}
        
    def Activated(self):
        FreeCADGui.addModule("FingerJoint")
        FreeCADGui.doCommand("FingerJoint.Create('FingerJoint')")
        
    def IsActive(self):
        return len(FreeCADGui.Selection.getSelection()) == 2

if FreeCAD.GuiUp:
    FreeCADGui.addCommand('FingerJoint',Command())
    w0 = FreeCADGui.activeWorkbench()
    FreeCADGui.activateWorkbench('CompleteWorkbench')
    w = FreeCADGui.getWorkbench('CompleteWorkbench')
    w.appendMenu('Joint', ['FingerJoint'])
    w.appendToolbar('Joint', ['FingerJoint'])
    FreeCADGui.activateWorkbench(w0.name())


def ConvertFingerJoiners():
    fingers = [o for o in FreeCAD.ActiveDocument.Objects if hasattr(o, 'Proxy') and isinstance(o.Proxy, FingerJoiner)]
    for f in fingers:
        f.addProperty('App::PropertyString',   'BaseJoint',   'Joint',  QtCore.QT_TRANSLATE_NOOP('FingerJoint', 'One body to add joint to'))
        f.addProperty('App::PropertyString',   'ToolJoint',   'Joint',  QtCore.QT_TRANSLATE_NOOP('FingerJoint', 'Another body to add joint to'))
        f.BaseJoint = f.Base.Name
        f.ToolJoint = f.Tool.Name
        f.removeProperty('Base')
        f.removeProperty('Tool')
