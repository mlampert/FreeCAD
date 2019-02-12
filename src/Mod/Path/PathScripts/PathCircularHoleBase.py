# -*- coding: utf-8 -*-

# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2017 sliptonic <shopinthewoods@gmail.com>               *
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 2 of     *
# *   the License, or (at your option) any later version.                   *
# *   for detail see the LICENCE text file.                                 *
# *                                                                         *
# *   This program is distributed in the hope that it will be useful,       *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# *   You should have received a copy of the GNU Library General Public     *
# *   License along with this program; if not, write to the Free Software   *
# *   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
# *   USA                                                                   *
# *                                                                         *
# ***************************************************************************

import ArchPanel
import FreeCAD
import DraftGeomUtils
import Part
import PathScripts.PathLog as PathLog
import PathScripts.PathOp as PathOp
import PathScripts.PathUtils as PathUtils
import sys

from PySide import QtCore

__title__ = "Path Circular Holes Base Operation"
__author__ = "sliptonic (Brad Collette)"
__url__ = "http://www.freecadweb.org"
__doc__ = "Base class an implementation for operations on circular holes."


# Qt tanslation handling
def translate(context, text, disambig=None):
    return QtCore.QCoreApplication.translate(context, text, disambig)


if False:
    PathLog.setLevel(PathLog.Level.DEBUG, PathLog.thisModule())
    PathLog.trackModule(PathLog.thisModule())
else:
    PathLog.setLevel(PathLog.Level.INFO, PathLog.thisModule())


def baseIsArchPanel(base):
    '''baseIsArchPanel(base) ... return true if op deals with an Arch.Panel.'''
    return hasattr(base, "Proxy") and isinstance(base.Proxy, ArchPanel.PanelSheet)

def getArchPanelEdge(base, sub):
    '''getArchPanelEdge(base, sub) ... helper function to identify a specific edge of an Arch.Panel.
    Edges are identified by 3 numbers:
        <holeId>.<wireId>.<edgeId>
    Let's say the edge is specified as "3.2.7", then the 7th edge of the 2nd wire in the 3rd hole returned
    by the panel sheet is the edge returned.
    Obviously this is as fragile as can be, but currently the best we can do while the panel sheets
    hide the actual features from Path and they can't be referenced directly.
    '''
    ids = sub.split('.')
    holeId = int(ids[0])
    wireId = int(ids[1])
    edgeId = int(ids[2])

    for holeNr, hole in enumerate(base.Proxy.getHoles(base, transform=True)):
        if holeNr == holeId:
            for wireNr, wire in enumerate(hole.Wires):
                if wireNr == wireId:
                    for edgeNr, edge in enumerate(wire.Edges):
                        if edgeNr == edgeId:
                            return edge

def getThetaAxisA(axis):
    theta = axis.getAngle(FreeCAD.Vector(0, 0, 1))
    if axis.y < 0:
        return -theta
    return theta

class CircularHole(object):
    def __init__(self, pos, dia, norm):
        self.pos = pos
        self.dia = dia
        self.norm = norm

    def position(self):
        '''position() ... returns a Vector for the position.
        Note that the value for Z is set to 0.'''
        return self.pos

    def diameter(self):
        '''diameter() ... returns the diameter.'''
        return self.dia

    def axis(self):
        '''axis() ... returns the axis of the hole.'''
        return self.norm

    def flipAxis(self):
        '''flipAxis() ... flips the direction of the axis.'''
        self.norm = -self.norm

    def getRotationMatrix(self):
        '''getRotationMatrix() ... returns the matrix to align the axis with the Z axis.'''
        theta = getThetaAxisA(self.norm)
        sin = math.sin(theta)
        cos = math.cos(theta)
        return FreeCAD.Matrix(1,0,0,0, 0,cos,-sin,0, 0,sin,cos,0, 0,0,0,0)


class LocationBasedCircularHole(CircularHole):

    def __init__(self, pos):
        super(self, self.__class__).__init__(pos, 0, FreeCAD.Vector(0, 0, 1))

class FeatureBasedCircularHole(CircularHole):
    '''Hole representation providing its features.'''

    def __init__(self, obj, base, sub):
        self.obj  = obj
        self.base = base
        self.sub  = sub
        self.shape = base.Shape.getElement(sub)
        self._setupHole()
        if not self.isAccessibleFrom(self.norm):
            self.flipAxis()

    def _setupHole(self):
        if hasattr(self.base, "Proxy") and isinstance(self.base.Proxy, ArchPanel.PanelSheet):
            self._setupHoleArchPanel()
        elif self.shape.ShapeType == 'Vertex':
            self._setupHoleVertex()
        elif self.shape.ShapeType == 'Edge' and hasattr(self.shape.Curve, 'Center'):
            self._setupHoleEdge()
        elif self.shape.ShapeType == 'Face':
            self._setupHoleFace()
        else:
            PathLog.error(translate("Path", "Feature %s.%s cannot be processed as a circular hole - please remove from Base geometry list.") % (self.base.Label, self.sub))
            return None
        return self

    def _setupHoleArchPanel(self):
        edge = getArchPanelEdge(self.base, self.sub)
        self.pos = edge.Curve.Center
        self.dia = edge.BoundBox.XLength
        self.norm = FreeCAD.Vector(0, 0, 1)

    def _setupHoleVertex(self):
        self.pos = self.shape.Point
        self.dia = 0
        self.norm = FreeCAD.Vector(0, 0, 1)

    def _setupHoleEdge(self):
        self.pos = self.shape.Curve.Center
        self.dia = self.shape.Curve.Radius * 2
        # orientation is undetermined
        self.norm = self.shape.Curve.Axis

    def _setupHoleFace(self):
        if hasattr(self.shape.Surface, 'Center'):
            self._setupHoleFaceHull()
        elif len(self.shape.Edges) == 1 and type(self.shape.Edges[0].Curve) == Part.Circle:
            self._setupHoleFaceBottom()

    def _setupHoleFaceHull(self):
        self.pos = self.shape.Surface.Center
        self.dia = self.shape.Surface.Radius * 2
        # orientation is undetermined
        self.norm = self.shape.Surface.Axis

    def _setupHoleFaceBottom(self):
        self.pos = self.shape.Edges[0].Curve.Center
        self.dia = self.shape.Edges[0].Curve.Radius * 2
        self.norm = self.shape.Surface.Axis if 'Forward' == self.shape.Orientation else -self.shape.Surface.Axis

    def isEnabled(self):
        '''isHoleEnabled(obj, base, sub) ... return true if hole is enabled.'''
        name = "%s.%s" % (self.base.Name, self.sub)
        return not name in self.obj.Disabled

    def isAccessibleFrom(self, vector):
        '''isAccessibleFrom(vector) ... returns true if the hole can be reached through vector.'''
        nv = vector.normalize()

        # "A hole is only accessible if vector is parallel to the hole's axis."
        if PathGeom.pointsCoincide(self.norm, nv) or PathGeom.pointsCoincide(self.norm, -nv):
            # "A hole is accessible if a laser from the center of the hole along its axis in the
            # given direction of vector does not intersect with the base."
            # There are edge conditions where above statement is not true - but for now we roll with that.
            startPt = self.pos
            endPt = startPt + self.base.Shape.BoundBox.DiagonalLength * vector
            laser = Part.LineSegment(startPt, endPt)
            if not PathGeom.isRoughly(0, self.base.Shape.distToShape(Part.Edge(laser))[0]):
                return True
        return False

class ObjectOp(PathOp.ObjectOp):
    '''Base class for proxy objects of all operations on circular holes.'''

    def opFeatures(self, obj):
        '''opFeatures(obj) ... calls circularHoleFeatures(obj) and ORs in the standard features required for processing circular holes.
        Do not overwrite, implement circularHoleFeatures(obj) instead'''
        return PathOp.FeatureTool | PathOp.FeatureDepths | PathOp.FeatureHeights | PathOp.FeatureBaseFaces | self.circularHoleFeatures(obj)

    def circularHoleFeatures(self, obj):
        '''circularHoleFeatures(obj) ... overwrite to add operations specific features.
        Can safely be overwritten by subclasses.'''
        return 0

    def initOperation(self, obj):
        '''initOperation(obj) ... adds Disabled properties and calls initCircularHoleOperation(obj).
        Do not overwrite, implement initCircularHoleOperation(obj) instead.'''
        obj.addProperty("App::PropertyStringList", "Disabled", "Base", QtCore.QT_TRANSLATE_NOOP("Path", "List of disabled features"))
        self.initCircularHoleOperation(obj)

    def initCircularHoleOperation(self, obj):
        '''initCircularHoleOperation(obj) ... overwrite if the subclass needs initialisation.
        Can safely be overwritten by subclasses.'''
        pass

    def holeDiameter(self, obj, base, sub):
        '''holeDiameter(obj, base, sub) ... returns the diameter of the specified hole.'''
        if baseIsArchPanel(base):
            edge = getArchPanelEdge(base, sub)
            return edge.BoundBox.XLength

        shape = base.Shape.getElement(sub)
        if shape.ShapeType == 'Vertex':
            return 0

        if shape.ShapeType == 'Edge' and type(shape.Curve) == Part.Circle:
            return shape.Curve.Radius * 2

        # for all other shapes the diameter is just the dimension in X
        return shape.BoundBox.XLength

    def isHoleEnabled(self, obj, base, sub):
        '''isHoleEnabled(obj, base, sub) ... return true if hole is enabled.'''
        name = "%s.%s" % (base.Name, sub)
        return not name in obj.Disabled

    def getHoles(self, obj):
        '''getHoles() ...  answer the collection of all holes.'''

        def haveLocations(self, obj):
            if PathOp.FeatureLocations & self.opFeatures(obj):
                return len(obj.Locations) != 0
            return False

        holes = []
        for base, subs in obj.Base:
            for sub in subs:
                holes.append(FeatureBasedCircularHole(obj, base, sub))

        if haveLocations(self, obj):
            for location in obj.Locations:
                holes.append(LocationBasedCircularHole(location))

        return holes

    def alignAxisTo(self, obj, axis, dest = None):
        theta = getThetaAxisA(axis)
        angle = theta * 180 / math.pi
        obj.OpStockZMax = obj.OpStockRadiusA
        obj.OpStockZMin = -obj.OpStockRadiusA
        self.commandlist.append(Path.Command('G0', {'Z': obj.getPropertyValue('ClearanceHeight').Value, 'F': self.vertRapid}))

        params = {'A': angle}
        # if we know where we want to end up once turned, we might as well reposition while turning
        if dest:
            params.update({'X': dest['x'], 'Y': dest['y']})

        self.commandlist.append(Path.Command('G0', params))

    def opExecute(self, obj):
        '''opExecute(obj) ... processes all Base features and Locations and collects
        them in a list of positions and radii which is then passed to circularHoleExecute(obj, holes).
        If no Base geometries and no Locations are present, the job's Base is inspected and all
        drillable features are added to Base. In this case appropriate values for depths are also
        calculated and assigned.
        Do not overwrite, implement circularHoleExecute(obj, holes) instead.'''
        PathLog.track()

        holes = self.getHoles(obj)

        zAxis = FreeCAD.Vector(0, 0, 1)
        # Start out aligned to Z axis, and rotation is a noop
        axis = zAxis
        rotm = FreeCAD.Matrix(1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,0)

        def rotateHole(hole, m):
            v = m.multVec(hole.position())
            return {'x': v.x, 'y': v.y, 'z': v.z, 'd': hole.diameter() / 2}

        for i,h in enumerate(holes):
            PathLog.debug("hole #%d: axis = (%.2f, %.2f, %.2f)" % (i, h.norm.x, h.norm.y, h.norm.z))

        while holes:
            aligned = [hole for hole in holes if hole.isAccessibleFrom(axis)]
            PathLog.debug("%d holes aligned with (%.2f, %.2f, %.2f)" % (len(aligned), axis.x, axis.y, axis.z))
            if aligned:
                self.circularHoleExecute(obj, [rotateHole(v, rotm) for v in aligned])
                holes = [hole for hole in holes if not hole in aligned]
            PathLog.debug("  %d left" % (len(holes)))
            if holes:
                hole = holes[0]
                axis = hole.axis()
                rotm = hole.getRotationMatrix()
                self.alignAxisTo(obj, axis, rotateHole(hole, rotm))
        if not PathGeom.pointsCoincide(axis, zAxis):
            self.alignAxisTo(obj, zAxis)

    def circularHoleExecute(self, obj, holes):
        '''circularHoleExecute(obj, holes) ... implement processing of holes.
        holes is a list of dictionaries with 'x', 'y' and 'd' specified for each hole.
        Note that for Vertexes, non-circular Edges and Locations r=0.
        Must be overwritten by subclasses.'''
        pass

    def findAllHoles(self, obj):
        if not self.getJob(obj):
            return
        features = []
        if 1 == len(self.model) and baseIsArchPanel(self.model[0]):
            panel = self.model[0]
            holeshapes = panel.Proxy.getHoles(panel, transform=True)
            tooldiameter = obj.ToolController.Proxy.getTool(obj.ToolController).Diameter
            for holeNr, hole in enumerate(holeshapes):
                PathLog.debug('Entering new HoleShape')
                for wireNr, wire in enumerate(hole.Wires):
                    PathLog.debug('Entering new Wire')
                    for edgeNr, edge in enumerate(wire.Edges):
                        if PathUtils.isDrillable(panel, edge, tooldiameter):
                            PathLog.debug('Found drillable hole edges: {}'.format(edge))
                            features.append((panel, "%d.%d.%d" % (holeNr, wireNr, edgeNr)))
        else:
            for base in self.model:
                features.extend(self.findHoles(obj, base))
        obj.Base = features
        obj.Disabled = []

    def findHoles(self, obj, baseobject):
        '''findHoles(obj, baseobject) ... inspect baseobject and identify all features that resemble a straight cricular hole.'''
        shape = baseobject.Shape
        PathLog.track('obj: {} shape: {}'.format(obj, shape))
        holelist = []
        features = []
        # tooldiameter = obj.ToolController.Proxy.getTool(obj.ToolController).Diameter
        tooldiameter = None
        PathLog.debug('search for holes larger than tooldiameter: {}: '.format(tooldiameter))
        if DraftGeomUtils.isPlanar(shape):
            PathLog.debug("shape is planar")
            for i in range(len(shape.Edges)):
                candidateEdgeName = "Edge" + str(i + 1)
                e = shape.getElement(candidateEdgeName)
                if PathUtils.isDrillable(shape, e, tooldiameter):
                    PathLog.debug('edge candidate: {} (hash {})is drillable '.format(e, e.hashCode()))
                    x = e.Curve.Center.x
                    y = e.Curve.Center.y
                    diameter = e.BoundBox.XLength
                    holelist.append({'featureName': candidateEdgeName, 'feature': e, 'x': x, 'y': y, 'd': diameter, 'enabled': True})
                    features.append((baseobject, candidateEdgeName))
                    PathLog.debug("Found hole feature %s.%s" % (baseobject.Label, candidateEdgeName))
        else:
            PathLog.debug("shape is not planar")
            for i in range(len(shape.Faces)):
                candidateFaceName = "Face" + str(i + 1)
                f = shape.getElement(candidateFaceName)
                if PathUtils.isDrillable(shape, f, tooldiameter):
                    PathLog.debug('face candidate: {} is drillable '.format(f))
                    if hasattr(f.Surface, 'Center'):
                        x = f.Surface.Center.x
                        y = f.Surface.Center.y
                        diameter = f.BoundBox.XLength
                    else:
                        center = f.Edges[0].Curve.Center
                        x = center.x
                        y = center.y
                        diameter = f.Edges[0].Curve.Radius * 2
                    holelist.append({'featureName': candidateFaceName, 'feature': f, 'x': x, 'y': y, 'd': diameter, 'enabled': True})
                    features.append((baseobject, candidateFaceName))
                    PathLog.debug("Found hole feature %s.%s" % (baseobject.Label, candidateFaceName))

        PathLog.debug("holes found: {}".format(holelist))
        return features
