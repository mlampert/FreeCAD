import FreeCAD
import Part
import math

from PySide import QtCore

DefaultLength = 20
'''
DefaultLength = 20 ... the lenght of joints used when they get created.
no doc strings for variables though :(
'''

if FreeCAD.GuiUp:
    import FreeCADGui
    from PySide import QtGui

def getNormal(face):
    normal = face.Surface.Axis
    normal.normalize()
    if face.Orientation == 'Reversed':
        normal *= -1
    return normal


class JointValues:
    '''internal class used by Joint to compute and hold all intermediary results - handy for debugging'''

    def __init__(self, joinerObject, joint):
        self.joiner = joinerObject.Proxy
        self.joint  = joint

        joiner = self.joiner
        joiner.setObject(joinerObject)

        self.jointBase = joiner.obj.Document.getObject(joiner.obj.BaseJoint)
        self.jointTool = joiner.obj.Document.getObject(joiner.obj.ToolJoint)
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

            self.length = joiner.obj.Length.Value
            self.offsetBase = joiner.obj.Offset.Value
            self.offsetTool = self.offsetBase + self.length

            self.extraLength = joiner.obj.ExtraLength.Value
            self.extraWidth  = joiner.obj.ExtraWidth.Value
            self.extraDepth  = joiner.obj.ExtraDepth.Value
        else:
            self.dimBase = 0
            self.dimTool = 0

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
        return self.offsetBase

    def jointSlackFor(self, joint):
        if joint == self.jointBase:
            return FreeCAD.Vector(self.extraLength, -self.extraWidth, self.extraDepth)
        return FreeCAD.Vector(self.extraLength, self.extraWidth, self.extraDepth)

    def jointStartWithCut(self, joint):
        return joint != self.jointBase


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
            #print("simple edge")
            edge = section.Edges[0]
        else:
            # this can happen if the edge is interrupted by pockets, most likely from
            # another FingerJoint operation
            #print("stukko edge")
            self.rogueEdges = section.Edges
            curve = section.Edges[0].Curve
            pts = [v.Point for e in section.Edges for v in e.Vertexes]
            params = [curve.parameter(p) for p in pts]
            minParam = min(params)
            maxParam = max(params)
            #print("stukko from %.2f to %.2f" % (minParam, maxParam))
            begin = curve.value(minParam)
            end   = curve.value(maxParam)
            #print("stukko start(%.2f, %.2f, %.2f) end(%.2f, %.2f, %.2f)" % (begin.x, begin.y, begin.z, end.x, end.y, end.z))
            edge = Part.Edge(Part.LineSegment(begin, end))

        n1 = getNormal(face)
        n2 = getNormal(cutFace)
        #print("getEdge n1(%.2f, %.2f, %.2f) n2(%.2f, %.2f, %.2f)" % (n1.x, n1.y, n1.z, n2.x, n2.y, n2.z))
        nDir = n1.cross(n2)
        if FreeCAD.Vector() == nDir:
            # seems we've lost track of one of our faces ...
            print("%s face=%s" % (self.joint.name, self.joint.obj.Face[1][0]))
        eDir = edge.Vertexes[1].Point - edge.Vertexes[0].Point
        #print("getEdge nDir(%.2f, %.2f, %.2f) eDir(%.2f, %.2f, %.2f)" % (nDir.x, nDir.y, nDir.z, eDir.x, eDir.y, eDir.z))

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

class Joint:
    '''Class that performs the actual joint modification on the base object.'''
     

    def __init__(self, obj, base, face, joiner):
        obj.addProperty('App::PropertyLinkSub',  'Face',       'FingerJoint', QtCore.QT_TRANSLATE_NOOP('FingerJoint', 'The actual Face used for calculating the cuts.'))
        obj.addProperty('App::PropertyLink',     'Joiner',     'FingerJoint', QtCore.QT_TRANSLATE_NOOP('FingerJoint', 'The object coordinating the joint.'))
        obj.addProperty('App::PropertyDistance', 'ExtraDepth', 'FingerJoint', QtCore.QT_TRANSLATE_NOOP('FingerJoint', 'Extra depth applied to joint cut.'))
        obj.addProperty('App::PropertyDistance', 'ExtraWidth', 'FingerJoint', QtCore.QT_TRANSLATE_NOOP('FingerJoint', 'Extra width applied to joint cut.'))
        obj.Proxy = self

        obj.Face     = (base, face)
        obj.Joiner   = joiner

    def __getstate__(self):
        return None
    def __setstate__(self, state):
        return None

    def getBaseShape(self, obj):
        '''returns base shape, positioned and oriented in world CS'''
        body = obj.Face[0].getParentGeoFeatureGroup()
        return body.Shape if body else obj.Face[0].Shape

    def getBaseFace(self, obj):
        '''returns base face, positioned and oriented in world CS'''
        return self.getBaseShape(obj).getElement(obj.Face[1][0])

    def execute(self, obj):
        #print("%s" % obj.Name)
        if not hasattr(obj, 'Joiner'):
            print("%s no Joiner" % (obj.Name))
            return None
        if not hasattr(self, 'obj'):
            self.obj = obj

        self.name   = obj.Name
        self.values = JointValues(obj.Joiner, self)
        if self.values.jointIsValidFor(obj):
            self.solid  = self.values.jointShapeFor(obj)
            self.face   = self.values.jointFaceFor(obj)
            self.edge   = self.values.jointEdgeFor(obj)
            self.dim    = self.values.jointDimensionsFor(obj)
            self.offset = self.values.jointOffsetFor(obj)
            self.startWithCut = self.values.jointStartWithCut(obj)
            self.slack  = self.values.jointSlackFor(obj)
            if 'ExtraDepth' in obj.PropertiesList:
                self.slack.z += obj.ExtraDepth.Value
            self.shape  = self.featherSolid(self.solid, self.face, self.edge, self.dim, self.startWithCut, self.offset, self.slack, obj.ExtraWidth.Value)
            obj.Shape   = self.shape
        else:
            print("%s invalid" % (self.name))
            obj.Shape = self.getBaseShape(obj)

    def featherSolid(self, solid, face, edge, dim, startWithCut, offset=0, slack = FreeCAD.Vector(0,0,0), extend=0):
        '''
        featherSolid(solid, face, edge, dim, offst=0) .... create finger joint feathers,
          solid  ... the solid to feature
          face   ... a face on the solid
          edge   ... an edge on the face along which to feather
          dim    ... vector of feather dimensions Vector(length, width, depth)
          startWithCut    ... set to True if the joint starts with a cut, False if it should start with a notch
          offset = 0      ... offset from the edge's starting point to the first feather cut
          slack  = (0,0,) ... vector of extra material to be removed in each direction (length, width, depth)
          extend = 0      ... extend the width of the finger in one direction by given amount
                     positive values are in finger direction, negative values in opposite direction
        '''

        # First determine the directions of the feathers
        self.normal = getNormal(face)
        self.dirDepth = FreeCAD.Vector() - self.normal
        self.dirLength = (edge.Vertexes[1].Point - edge.Vertexes[0].Point).normalize()
        self.dirWidth  = self.dirDepth.cross(self.dirLength)

        # there's a possibility this will always be 1.0 ....
        self.scale = (edge.LastParameter - edge.FirstParameter) / edge.Length

        self.start = edge.Vertexes[0].Point

        pts = []
        p0 = self.start
        pts.append(p0)

        width = dim.y + slack.y
        if extend > 0:
            if width > 0:
                width += extend
            else:
                width -= extend
        p1 = p0 + self.dirWidth * self.scale * width
        pts.append(p1)

        # depth cut
        self.eDepth  = self.dirDepth * self.scale * (dim.z + slack.z)

        p2 = p1 + self.eDepth
        pts.append(p2)
        if math.fabs(slack.y) > 0.00001 or extend < 0:
            backWidth = slack.y
            if extend < 0:
                if backWidth > 0:
                    backWidth -= extend
                else:
                    backWidth += extend
            p4 = p0 - self.dirWidth * self.scale * backWidth
            p3 = p4 + self.eDepth
            pts.append(p3)
            pts.append(p4)
        else:
            p3 = p0 + self.eDepth
            pts.append(p3)
        pts.append(p0)

        self.cutPoints = pts
        self.cutWire = Part.makePolygon(pts)
        self.cutFace = Part.Face(self.cutWire)

        # create solid we can use as a template
        self.cutSolid = self.extrudeCutFace(dim.x, slack.x)

        diff  = self.dirLength * self.scale * self.dim.x
        trans = self.dirLength * self.scale * offset + diff
        self.cut = []

        if startWithCut:
            initialLength = dim.x + offset
            cut = self.extrudeCutFace(initialLength, slack.x)
            self.cut.append(cut)
            trans  += diff
            offset += dim.x
            #print("%s start with %.2f" % (self.name, initialLength))
        #print("%s start(%.2f, %.2f, %.2f)" % (self.name, p0.x, p0.y, p0.z))
        #print("%s trans(%.2f, %.2f, %.2f)" % (self.name, trans.x, trans.y, trans.z))

        offset += dim.x
        while offset + dim.x < edge.Length:
            #print("  %.2f / %.2f" % (offset, edge.Length))
            cut = self.cutSolid.copy()
            cut.translate(trans)
            self.cut.append(cut)
            trans  += 2 * diff
            offset += 2 * dim.x

        if offset < edge.Length:
            finalLength = edge.Length - offset
            cut = self.extrudeCutFace(finalLength, slack.x)
            cut.translate(trans)
            self.cut.append(cut)
            #print("%s end with %.2f" % (self.name, finalLength))

        #print('')
        self.cutOuts = Part.makeCompound(self.cut)
        return solid.cut(self.cutOuts)

    def extrudeCutFace(self, length, slack):
        '''helper function that extrudes the basic cut with a given length and adds given slack on both ends.'''
        solid = self.cutFace.extrude(self.dirLength * self.scale * (length + slack))
        if math.fabs(slack) > 0.000001:
            bwd = self.cutFace.extrude(self.dirLength * -1 * self.scale * slack)
            solid = solid.fuse(bwd)
        return solid

class FingerJoiner:
    '''POD for holding joint parameters used by both Joints attached to a Joiner.'''
    def __init__(self, obj, base, tool, lenght=100):
        obj.addProperty('App::PropertyString',   'BaseJoint',   'Joint',  QtCore.QT_TRANSLATE_NOOP('FingerJoint', 'One solid to add joint to'))
        obj.addProperty('App::PropertyString',   'ToolJoint',   'Joint',  QtCore.QT_TRANSLATE_NOOP('FingerJoint', 'Another solid to add joint to'))
        obj.addProperty('App::PropertyDistance', 'Length',      'Finger', QtCore.QT_TRANSLATE_NOOP('FingerJoint', 'The length of a joint incision/notch.'))
        obj.addProperty('App::PropertyDistance', 'Offset',      'Finger', QtCore.QT_TRANSLATE_NOOP('FingerJoint', 'Offset before the first joint finger.'))
        obj.addProperty('App::PropertyDistance', 'ExtraLength', 'Finger', QtCore.QT_TRANSLATE_NOOP('FingerJoint', 'Extra length applied to both joint cuts on both sides.'))
        obj.addProperty('App::PropertyDistance', 'ExtraWidth',  'Finger', QtCore.QT_TRANSLATE_NOOP('FingerJoint', 'Extra width applied to both joint cuts on both sides.'))
        obj.addProperty('App::PropertyDistance', 'ExtraDepth',  'Finger', QtCore.QT_TRANSLATE_NOOP('FingerJoint', 'Extra depth applied to both joint cut.'))

        obj.Proxy = self
        obj.BaseJoint = base.Name
        obj.ToolJoint = tool.Name
        obj.Length = lenght

        obj.setEditorMode('BaseJoint', 1) # ro
        obj.setEditorMode('ToolJoint', 1) # ro
        obj.setEditorMode('Placement', 2) # hide

    def __getstate__(self):
        return None
    def __setstate__(self, state):
        return None

    def setObject(self, obj):
        self.obj = obj

    def execute(self, obj):
        #print("%s(%s, %s)" % (obj.Name, obj.BaseJoint, obj.ToolJoint))
        if not hasattr(self, 'obj'):
            self.obj = obj

        self.jointBase = obj.Document.getObject(obj.BaseJoint)
        self.jointTool = obj.Document.getObject(obj.ToolJoint)

        self.shapeBase = self.jointBase.Proxy.getBaseShape(self.jointBase)
        self.shapeTool = self.jointTool.Proxy.getBaseShape(self.jointTool)

        self.cutShape = self.shapeBase.common(self.shapeTool)
        obj.Shape = self.cutShape

class ViewProviderJoiner:
    def __init__(self, vobj):
        vobj.Proxy = self
        self.vobj = vobj
        self.obj = vobj.Object

    def attach(self, vobj):
        self.Object = vobj.Object

    def getIcon(self):
        return Command.Icon

    def __getstate__(self):
        return None
    def __setstate__(self, state):
        return None

class ViewProviderJoint:
    def __init__(self, vobj):
        vobj.Proxy = self
        self.vobj = vobj

    def getChild(self):
        obj = self.obj.Face[0]
        body = obj.getParentGeoFeatureGroup()
        return body if body else obj

    def attach(self, vobj):
        self.vobj = vobj
        self.obj = vobj.Object
        self.joint = vobj.Object.Proxy

        baseVobj = self.getChild().ViewObject
        baseVobj.Visibility = False
        vobj.DiffuseColor = baseVobj.DiffuseColor
        vobj.Transparency = baseVobj.Transparency

    def claimChildren(self):
        return [self.getChild()]

    def getIcon(self):
        return Command.Icon

    def __getstate__(self):
        return None
    def __setstate__(self, state):
        return None

def Create(name):
    def createJoint(obj, face, joiner):
        name  = obj.Name
        label = obj.Label
        group = obj.getParentGeoFeatureGroup()
        if group:
            name  = group.Name
            label = group.Label

        joint = FreeCAD.ActiveDocument.addObject('Part::FeaturePython', name)
        joint.Label = label
        proxy = Joint(joint, obj, face, joiner)
        return (joint, proxy)

    sel = FreeCADGui.Selection.getSelectionEx()
    if len(sel) == 2 and len(sel[0].SubObjects) == 1 and len(sel[1].SubObjects) == 1:
        FreeCAD.ActiveDocument.openTransaction("Create finger joint")
        joiner = FreeCAD.ActiveDocument.addObject('Part::FeaturePython', name)

        (o0, p0) = createJoint(sel[0].Object, sel[0].SubElementNames[0], joiner)
        (o1, p1) = createJoint(sel[1].Object, sel[1].SubElementNames[0], joiner)

        finger = FingerJoiner(joiner, o0, o1, DefaultLength)

        if FreeCAD.GuiUp:
            ViewProviderJoiner(joiner.ViewObject)
            joiner.ViewObject.Visibility = False
            ViewProviderJoint(o0.ViewObject)
            ViewProviderJoint(o1.ViewObject)

        FreeCAD.ActiveDocument.commitTransaction()
        FreeCAD.ActiveDocument.recompute()
        return joiner

    else:
        return None


class Command:
    Icon = 'FingerJoint.svg'

    def GetResources(self):
        return {'Pixmap'  : self.Icon,
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


def getAllJoiners():
    '''Returns all Joiner objects in the active document.'''
    return [o for o in FreeCAD.ActiveDocument.Objects if hasattr(o, 'BaseJoint') and hasattr(o, 'ToolJoint')]

def getAllJoints():
    '''Returns all Joint objects in the active document.'''
    return [o for o in FreeCAD.ActiveDocument.Objects if hasattr(o, 'Joiner')]

def touchAll():
    '''
    Marks all Joiner objects in the active document for recomputation.
    This can be handy if a lot of parts move around because the counterpart of a Joint does not get updated automatically.
    '''
    for j in getAllJoiners():
        j.touch()

def setAllExtra(length = None, width = None, depth = None):
    '''
    setAllExtra(lenght, width, depth) ... all parameters optional.
    Sets the extra values on all Joiner objects in the current document, regardless of waht they were before.
    '''
    for o in getAllJoiners():
        if length is not None:
            o.ExtraLength = length
        if width is not None:
            o.ExtraWidth = width
        if depth is not None:
            o.ExtraDepth = depth
