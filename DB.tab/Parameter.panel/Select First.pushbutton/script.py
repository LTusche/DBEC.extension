# -*- coding=utf-8 -*-
# import math

from pyrevit import revit, DB, UI
from pyrevit.framework import List
from Autodesk.Revit import Exceptions

uidoc = revit.uidoc # type: UI.UIDocument
doc = revit.doc # type: DB.Document

active_selection = uidoc.Selection.GetElementIds()

uidoc.Selection.SetElementIds(List[DB.ElementId]([active_selection[0]]))