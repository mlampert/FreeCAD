# -*- coding: utf-8 -*-
# ***************************************************************************
# *   Copyright (c) 2019 sliptonic <shopinthewoods@gmail.com>               *
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

import FreeCADGui
import PathScripts.PathGui as PathGui
import PathScripts.PathLog as PathLog
import PathScripts.PathPreferences as PathPreferences
import PathScripts.PathToolBit as PathToolBit
import os
import re

from PySide import QtCore, QtGui

PathLog.setLevel(PathLog.Level.INFO, PathLog.thisModule())
# PathLog.trackModule(PathLog.thisModule())


# Qt translation handling
def translate(context, text, disambig=None):
    return QtCore.QCoreApplication.translate(context, text, disambig)


class ToolBitEditor(object):
    '''UI and controller for editing a ToolBit.
    The controller embeds the UI to the parentWidget which has to have a
    layout attached to it.
    '''

    def __init__(self, tool, parentWidget=None, loadBitBody=True):
        PathLog.track()
        self.form = FreeCADGui.PySideUic.loadUi(":/panels/ToolBitEditor.ui")

        if parentWidget:
            self.form.setParent(parentWidget)
            parentWidget.layout().addWidget(self.form)

        self.tool = tool
        self.loadbitbody = loadBitBody
        if not tool.BitShape:
            self.tool.BitShape = 'endmill.fcstd'

        if self.loadbitbody:
            self.tool.Proxy.loadBitBody(self.tool)

        # remove example widgets
        layout = self.form.bitParams.layout()
        for i in range(layout.rowCount() - 1, -1, -1):
            layout.removeRow(i)
        # used to track property widgets and editors
        self.widgets = []

        self.setupTool(self.tool)

    def setupTool(self, tool):
        PathLog.track()
        # Can't delete and add fields to the form because of dangling references in case of
        # a focus change. see https://forum.freecadweb.org/viewtopic.php?f=10&t=52246#p458583
        # Instead we keep widgets once created and use them for new properties, and hide all
        # which aren't being needed anymore.

        def labelText(name):
            return re.sub('([A-Z][a-z]+)', r' \1', re.sub('([A-Z]+)', r' \1', name))

        layout = self.form.bitParams.layout()
        ui = FreeCADGui.UiLoader()

        # for all properties either assign them to existing labels and editors
        # or create additional ones for them if not enough have already been
        # created.
        for nr, name in enumerate(tool.Proxy.toolShapeProperties(tool)):
            if nr < len(self.widgets):
                PathLog.debug("re-use row: {} [{}]".format(nr, name))
                label, qsb, editor = self.widgets[nr]
                label.setText(labelText(name))
                editor.attachTo(tool, name)
                label.show()
                qsb.show()
            else:
                qsb    = ui.createWidget('Gui::QuantitySpinBox')
                editor = PathGui.QuantitySpinBox(qsb, tool, name)
                label  = QtGui.QLabel(labelText(name))
                self.widgets.append((label, qsb, editor))
                PathLog.debug("create row: {} [{}]  {}".format(nr, name, type(qsb)))
                if hasattr(qsb, 'editingFinished'):
                    qsb.editingFinished.connect(self.updateTool)

            if nr >= layout.rowCount():
                layout.addRow(label, qsb)

        # hide all rows which aren't being used
        for i in range(len(tool.BitPropertyNames), len(self.widgets)):
            label, qsb, editor = self.widgets[i]
            label.hide()
            qsb.hide()
            editor.attachTo(None)
            PathLog.debug("  hide row: {}".format(i))

        img = tool.Proxy.getBitThumbnail(tool)
        if img:
            self.form.image.setPixmap(QtGui.QPixmap(QtGui.QImage.fromData(img)))
        else:
            self.form.image.setPixmap(QtGui.QPixmap())

    def accept(self):
        PathLog.track()
        self.refresh()
        self.tool.Proxy.unloadBitBody(self.tool)

    def reject(self):
        PathLog.track()
        self.tool.Proxy.unloadBitBody(self.tool)

    def updateUI(self):
        PathLog.track()
        self.form.toolName.setText(self.tool.Label)
        self.form.shapePath.setText(self.tool.BitShape)

        for lbl, qsb, editor in self.widgets:
            editor.updateSpinBox()

    def updateShape(self):
        PathLog.track()
        shapePath = str(self.form.shapePath.text())
        # Only need to go through this exercise if the shape actually changed.
        if self.tool.BitShape != shapePath:
            self.tool.BitShape = shapePath
            self.setupTool(self.tool)
            self.form.toolName.setText(self.tool.Label)

            for lbl, qsb, editor in self.widgets:
                editor.updateSpinBox()

    def updateTool(self):
        PathLog.track()

        label = str(self.form.toolName.text())
        shape = str(self.form.shapePath.text())
        if self.tool.Label != label:
            self.tool.Label = label
        if self.tool.BitShape != shape:
            self.tool.BitShape = shape

        for lbl, qsb, editor in self.widgets:
            editor.updateProperty()

        self.tool.Proxy._updateBitShape(self.tool)

    def refresh(self):
        PathLog.track()
        self.form.blockSignals(True)
        self.updateTool()
        self.updateUI()
        self.form.blockSignals(False)

    def selectShape(self):
        PathLog.track()
        path = self.tool.BitShape
        if not path:
            path = PathPreferences.lastPathToolShape()
        foo = QtGui.QFileDialog.getOpenFileName(self.form,
                                                "Path - Tool Shape",
                                                path,
                                                "*.fcstd")
        if foo and foo[0]:
            PathPreferences.setLastPathToolShape(os.path.dirname(foo[0]))
            self.form.shapePath.setText(foo[0])
            self.updateShape()

    def setupUI(self):
        PathLog.track()
        self.updateUI()

        self.form.toolName.editingFinished.connect(self.refresh)
        self.form.shapePath.editingFinished.connect(self.updateShape)
        self.form.shapeSet.clicked.connect(self.selectShape)
