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

import FreeCAD
import FreeCADGui
import PathScripts.PathGui as PathGui
import PathScripts.PathLog as PathLog
import PathScripts.PathPreferences as PathPreferences
import PathScripts.PathToolBit as PathToolBit
import PathScripts.PathUtil as PathUtil
import os
import re

from PySide import QtCore, QtGui

PathLog.setLevel(PathLog.Level.INFO, PathLog.thisModule())
# PathLog.trackModule(PathLog.thisModule())


# Qt translation handling
def translate(context, text, disambig=None):
    return QtCore.QCoreApplication.translate(context, text, disambig)

class _PropertyEditorBase(object):
    '''Base class of all typed property editors'''

    def __init__(self, obj, prop):
        self.obj = obj
        self.prop = prop
    def getValue(self):
        return getattr(self.obj, self.prop)
    def setValue(self, val):
        setattr(self.obj, self.prop, val)

class _PropertyEditorInteger(_PropertyEditorBase):
    def widget(self, parent):
        return QtGui.QSpinBox(parent)
    def setEditorData(self, widget):
        widget.setValue(self.getValue())
    def setModelData(self, widget):
        self.setValue(widget.value())

class _PropertyEditorFloat(_PropertyEditorInteger):
    def widget(self, parent):
        return QtGui.QDoubleSpinBox(parent)

class _PropertyEditorBool(_PropertyEditorBase):
    def widget(self, parent):
        return QtGui.QComboBox(parent)
    def setEditorData(self, widget):
        widget.clear()
        widget.addItems([str(False), str(True)])
        widget.setCurrentIndex(1 if self.getValue() else 0)
    def setModelData(self, widget):
        self.setValue(widget.currentIndex() == 1)

class _PropertyEditorString(_PropertyEditorBase):
    def widget(self, parent):
        return QtGui.QLineEdit(parent)
    def setEditorData(self, widget):
        widget.setText(self.getValue())
    def setModelData(self, widget):
        self.setValue(widget.text())

class _PropertyEditorQuantity(_PropertyEditorBase):
    def widget(self, parent):
        qsb = FreeCADGui.UiLoader().createWidget('Gui::QuantitySpinBox', parent)
        self.editor = PathGui.QuantitySpinBox(qsb, self.obj, self.prop)
        return qsb
    def setEditorData(self, widget):
        self.editor.updateSpinBox()
    def setModelData(self, widget):
        self.editor.updateProperty()

_PropertyEditorFactory = {
        bool                    : _PropertyEditorBool,
        int                     : _PropertyEditorInteger,
        float                   : _PropertyEditorFloat,
        str                     : _PropertyEditorString,
        FreeCAD.Units.Quantity  : _PropertyEditorQuantity,
        }

class _Delegate(QtGui.QStyledItemDelegate):
    '''Handles the creation of an appropriate editing widget for a given property.'''
    ObjectRole   = QtCore.Qt.UserRole + 1
    PropertyRole = QtCore.Qt.UserRole + 2
    EditorRole   = QtCore.Qt.UserRole + 3

    def createEditor(self, parent, option, index):
        editor = index.data(self.EditorRole)
        if editor is None:
            obj = index.data(self.ObjectRole)
            prp = index.data(self.PropertyRole)
            editor = _PropertyEditorFactory[type(getattr(obj, prp))](obj, prp)
            index.model().setData(index, editor, self.EditorRole)
        return editor.widget(parent)

    def setEditorData(self, widget, index):
        # called to update the widget with the current data
        index.data(self.EditorRole).setEditorData(widget)

    def setModelData(self, widget, model, index):
        # called to update the model with the data from the widget
        editor = index.data(self.EditorRole)
        editor.setModelData(widget)
        index.model().setData(index, PathUtil.getPropertyValueString(editor.obj, editor.prop), QtCore.Qt.DisplayRole)


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
        self.setupAttributes(self.tool)

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

    def setupAttributes(self, tool):
        PathLog.track()

        self.delegate = _Delegate(self.form.attrTree)
        self.model = QtGui.QStandardItemModel(self.form.attrTree)
        self.model.setHorizontalHeaderLabels(['Property', 'Value'])

        attributes = tool.Proxy.toolGroupsAndProperties(tool, False)
        for name in attributes:
            group = QtGui.QStandardItem()
            group.setData(name, QtCore.Qt.EditRole)
            group.setEditable(False)
            for prop in attributes[name]:
                label = QtGui.QStandardItem()
                label.setData(prop, QtCore.Qt.EditRole)
                label.setEditable(False)

                value = QtGui.QStandardItem()
                value.setData(PathUtil.getPropertyValueString(tool, prop), QtCore.Qt.DisplayRole)
                value.setData(tool, _Delegate.ObjectRole)
                value.setData(prop, _Delegate.PropertyRole)

                group.appendRow([label, value])
            self.model.appendRow(group)


        self.form.attrTree.setModel(self.model)
        self.form.attrTree.setItemDelegateForColumn(1, self.delegate)
        self.form.attrTree.expandAll()
        self.form.attrTree.resizeColumnToContents(0)
        self.form.attrTree.resizeColumnToContents(1)
        #self.form.attrTree.collapseAll()

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
