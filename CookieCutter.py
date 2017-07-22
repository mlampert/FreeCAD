import FreeCAD
import FreeCADGui
import Part
import PathScripts
import PathScripts.PathJob as PathJob
import copy
import sys

from PathScripts.PathGeom import PathGeom

class __TreeObject:
    '''Internal data object used to generate the tree of wires.'''
    def __init__(self, obj):
        self.obj  = obj
        self.children = []
        self.points = [FreeCAD.Vector(v.X, v.Y, v.Z) for v in obj.Shape.Vertexes]
        self.face = Part.Face(obj.Shape.Wires[0]) if obj.Shape.isClosed() else None

    def isInsideOf(self, tree):
        '''isInsideOf(tree) ... return True if any part of the receiver lies within tree'''
        return tree.face and tree.face.isInside(self.points[0], 0.001, True)

    def consoleDump(self, indent):
        '''consoleDump(indent) ... recursively print entire subtree'''
        print("%s%s" % (indent, self.obj.Label))
        for child in self.children:
            child.consoleDump(indent + '  ')

class CookieCutter:
    '''Wrapper object for any shape constructed from wires to be used by Arch.PanelSheet.'''
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

class CookieCutterViewProvider:
    '''ViewProvider for CookieCutter, claims children.'''
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
    '''CreateFromTree(tree, name) ... creates cookie cutters for all items.'''
    def createCookieCutter(o, children):
        obj = FreeCAD.ActiveDocument.addObject('Part::FeaturePython', 'CookieCutter')
        cut = CookieCutter(obj, o, children)
        if FreeCAD.GuiUp:
            CookieCutterViewProvider(obj.ViewObject)
        return obj

    def recursiveCreate(tree):
        children = [recursiveCreate(child) for child in tree.children]
        obj = createCookieCutter(tree.obj, children)
        return obj

    FreeCAD.ActiveDocument.openTransaction("Create CookieCutter hierarchy")
    objects = [recursiveCreate(obj) for obj in tree]
    FreeCAD.ActiveDocument.commitTransaction()
    return objects

def wiresAreIdentical(w0, w1):
    '''wiresAreIdentical(w0, w1) ... simple check if 2 wires form an identical shape.
    Note that the check just verifies that the vertices of the shapes match, it does
    not verify if there are an eqivalent amount of edges. Meaning a closed wire and
    a copy of the same with a missing edge will still be detected as identical.
    This is intentional due to the way in some SVGs all shapes are duplicated. If the
    user "fixes" the shape they most likely only fix one copy of the shape.'''
    w0points = [FreeCAD.Vector(v.X, v.Y, v.Z) for v in w0.Vertexes]
    w1points = [FreeCAD.Vector(v.X, v.Y, v.Z) for v in w1.Vertexes]
    if len(w0points) != len(w1points):
        return False
    for p0, p1 in zip(w0points, w1points):
        if not PathGeom.pointsCoincide(p0, p1):
            return False
    return True

def removeDuplicates(objects):
    '''removeDuplicates(objects) ... looks for identical wires and only keeps one copy.
    All returned shapes have are closed (all others are rejected as well).'''
    unique = []
    for obj in objects:
        if obj.Shape.isClosed():
            dup = False
            for o in unique:
                if wiresAreIdentical(obj.Shape, o.Shape):
                    dup = True
                    break
            if not dup:
                unique.append(obj)
    return unique

def removeFrame(objects):
    '''removeFrame(objects) ... tries to determine if one of the shapes is a frame
    enclosing all others. If it finds one of those it will remove it.'''
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
    '''buildTree(objects) ... constructs a tree where each element holds its path and all shapes it surrounds'''
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
    '''dumpTree(tree) ... print tree to console - simple debugging tool'''
    for t in tree:
        t.consoleDump('- ')

def doall(removeUnused = False):
    '''doall(removeUnused=False) ... Preps all objects of the current document
    and constructs CookieCutters for them and adds those into a Arch.PanelSheet.
    It creates a PathJob from a template and - hopefully soon - automatically
    generates the Path for it.'''
    import Arch
    objects = FreeCAD.ActiveDocument.Objects
    objects = removeDuplicates(objects)
    objects = removeFrame(objects)
    if removeUnused:
        for o in FreeCAD.ActiveDocument.Objects:
            if not o in objects:
                FreeCAD.ActiveDocument.removeObject(o.Name)
    t = buildTree(objects)
    FreeCAD.ActiveDocument.recompute()
    o = CreateFromTree(t, 'CookieCutter')
    FreeCAD.ActiveDocument.recompute()
    s = Arch.makePanelSheet(o, 'PanelSheet')
    FreeCAD.ActiveDocument.recompute()
    j = PathJob.CommandJobCreate.Execute(s, '/home/markus/src/macros/path/job_mine.xml')
    FreeCAD.ActiveDocument.recompute()

def doit():
    '''doit() ... test script to load 'pumpkin' and call doall'''
    if 'pumpkin' in FreeCAD.listDocuments():
        FreeCAD.closeDocument('pumpkin')
    FreeCAD.open('pumpkin.fcstd')
    doall()

if FreeCAD.GuiUp:
    FreeCADGui.addModule('CookieCutter')

print("arguments = %s" % sys.argv)
