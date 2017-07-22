import FreeCAD
import FreeCADGui
import Part
import PathScripts
import PathScripts.PathJob as PathJob
import copy
import sys

from PathScripts.PathGeom import PathGeom

class __TreeObject:
    def __init__(self, obj):
        self.obj  = obj
        self.children = []
        self.points = [FreeCAD.Vector(v.X, v.Y, v.Z) for v in obj.Shape.Vertexes]
        self.face = Part.Face(obj.Shape.Wires[0]) if obj.Shape.isClosed() else None

    def isInsideOf(self, tree):
        '''isInsideOf(tree) ... return True if any part of the receiver lies within tree'''
        return tree.face and tree.face.isInside(self.points[0], 0.001, True)

    def consoleDump(self, indent):
        print("%s%s" % (indent, self.obj.Label))
        for child in self.children:
            child.consoleDump(indent + '  ')

class CookieCutter:
    def __init__(self, obj, outline, children):
        obj.addProperty('App::PropertyLinkList', 'Children', 'CookieCutter', 'List of child shapes')
        obj.addProperty('App::PropertyLink',     'Outline',  'CookieCutter', 'The outline of the drawing.')
        obj.Children = children
        obj.Outline  = outline
        obj.Proxy    = self

    def __getstate__(self):
        return None
    def __setstate__(self, state):
        return None

    def execute(self, obj):
        wires = obj.Outline.Shape.Wires
        for child in obj.Children:
            wires.extend(child.Shape.Wires)
        shape = Part.Compound(wires)
        obj.Shape = shape

    def getWires(self, obj):
        '''getWires() ... magic interface for PanelSheet'''
        outlines = obj.Outline.Shape.Wires
        holes = []
        for child in obj.Children:
            wires = child.Shape.Wires
            holes.extend(wires)
        out = Part.Compound(outlines)
        hol = Part.Compound(holes) if holes else None
        return (out, hol, None)

class DrawCutViewProvider:
    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        self.vobj = vobj
        for child in self.claimChildren():
            child.ViewObject.Visibility = False

    def __getstate__(self):
        return None
    def __setstate__(self, state):
        return None

    def claimChildren(self):
        children = [self.vobj.Object.Outline]
        children.extend(self.vobj.Object.Children)
        return children

def CreateFromTree(tree, name):
    def createDrawCut(o, children):
        obj = FreeCAD.ActiveDocument.addObject('Part::FeaturePython', 'CookieCutter')
        cut = CookieCutter(obj, o, children)
        if FreeCAD.GuiUp:
            DrawCutViewProvider(obj.ViewObject)
        return obj

    def recursiveCreate(tree):
        children = [recursiveCreate(child) for child in tree.children]
        obj = createDrawCut(tree.obj, children)
        return obj

    FreeCAD.ActiveDocument.openTransaction("Create CookieCutter hierarchy")
    objects = [recursiveCreate(obj) for obj in tree]
    FreeCAD.ActiveDocument.commitTransaction()
    return objects

def wiresAreIdentical(w0, w1):
    w0points = [FreeCAD.Vector(v.X, v.Y, v.Z) for v in w0.Vertexes]
    w1points = [FreeCAD.Vector(v.X, v.Y, v.Z) for v in w1.Vertexes]
    if len(w0points) != len(w1points):
        return False
    for p0, p1 in zip(w0points, w1points):
        if not PathGeom.pointsCoincide(p0, p1):
            return False
    return True

def removeDuplicates(objects):
    unique = []
    for obj in objects:
        dup = False
        for o in unique:
            if wiresAreIdentical(obj.Shape, o.Shape):
                dup = True
                break
        if not dup:
            unique.append(obj)
    return unique

def removeFrame(objects):
    result = copy.copy(objects)
    candidates = [o for o in objects if len(o.Shape.Vertexes) == 4]
    if candidates:
        biggest = sorted(candidates, key=lambda o: o.Shape.BoundBox.DiagonalLength)[-1]
        print("biggest = %s" % biggest.Label)
        b = FreeCAD.BoundBox()
        for o in objects:
            if o != biggest:
                b = b.united(o.Shape.BoundBox)
        if biggest.Shape.BoundBox.isInside(b):
            result.remove(biggest)
    return result



def buildTree(objects):
    def asTree(forrest):
        #print("asTree(%d)" % (len(forrest)))
        roots = []
        for (i,tree) in enumerate(forrest):
            isRoot = True
            for t in forrest:
                if t != tree and tree.isInsideOf(t):
                    #print("%s --> %s" % (tree.obj.Name, t.obj.Name))
                    t.children.append(tree)
                    isRoot = False
                    break
            if isRoot:
                roots.append(tree)
        for tree in roots:
            tree.children = asTree(tree.children)
        return roots
    #print("buildTree(%d)" % (len(objects)))
    return asTree([__TreeObject(o) for o in objects])

def dumpTree(tree):
    for t in tree:
        t.consoleDump('- ')

def doall():
    import Arch
    t = buildTree(FreeCAD.ActiveDocument.Objects)
    FreeCAD.ActiveDocument.recompute()
    o = CreateFromTree(t, 'CookieCutter')
    FreeCAD.ActiveDocument.recompute()
    s = Arch.makePanelSheet(o, 'PanelSheet')
    FreeCAD.ActiveDocument.recompute()
    j = PathJob.CommandJobCreate.Execute(s, '/home/markus/src/macros/path/job_mine.xml')
    FreeCAD.ActiveDocument.recompute()

def doit():
    if 'pumpkin' in FreeCAD.listDocuments():
        FreeCAD.closeDocument('pumpkin')
    FreeCAD.open('pumpkin.fcstd')
    doall()

FreeCADGui.addModule('CookieCutter')
print("arguments = %s" % sys.argv)
