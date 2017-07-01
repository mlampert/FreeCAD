import FreeCAD
import Part

from PySide import QtCore

if FreeCAD.GuiUp:
    import FreeCADGui
    from PySide import QtGui


class FingerJoint:

    def __init__(self, obj, body0, face0Name, body1, face1Name):
        self.Type = 'FingerJoint'
        obj.addProperty('App::PropertyLink', 'Body1', 'Base', QtCore.QT_TRANSLATE_NOOP('PartDesign_FingerJoint', 'One body to add joint to'))
        obj.addProperty('App::PropertyLink', 'Body2', 'Base', QtCore.QT_TRANSLATE_NOOP('PartDesign_FingerJoint', 'Another body to add joint to'))
        obj.addProperty('App::PropertyString', 'Body1Face', 'Base', QtCore.QT_TRANSLATE_NOOP('PartDesign_FingerJoint', 'An optional description for this job'))
        obj.addProperty('App::PropertyString', 'Body2Face', 'Base', QtCore.QT_TRANSLATE_NOOP('PartDesign_FingerJoint', 'An optional description for this job'))
        obj.Proxy = self
        self.obj = obj

        obj.Body1 = body0
        obj.Body2 = body1
        obj.Body1Face = face0Name
        obj.Body2Face = face1Name

    def execute(self,obj):
        pass

def Create(name):
    sel = FreeCADGui.Selection.getSelectionEx()
    if len(sel) == 2 and len(sel[0].SubObjects) == 1 and len(sel[1].SubObjects) == 1:
        print("Create finger joint %s" % (name))
        obj = FreeCAD.ActiveDocument.addObject("App::FeaturePython", name)
        proxy = FingerJoint(obj, sel[0].Object, sel[0].SubElementNames[0], sel[1].Object, sel[1].SubElementNames[0])
        return obj
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
        #FreeCADGui.doCommand("Gui.activeDocument().setEdit(App.ActiveDocument.ActiveObject.Name,0)")
        
    def IsActive(self):
        return len(FreeCADGui.Selection.getSelection()) == 2

if FreeCAD.GuiUp:
    FreeCADGui.addCommand('PartDesign_FingerJoint',Command())
