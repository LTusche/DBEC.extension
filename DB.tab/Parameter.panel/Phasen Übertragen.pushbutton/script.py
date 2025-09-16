# -*- coding=utf-8 -*-

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from Autodesk.Revit.UI import UIApplication
    __revit__ = UIApplication()

from System.Collections import Generic

from Autodesk.Revit import DB, UI
from Autodesk.Revit import Exceptions as rvtException
import traceback

uiapp = __revit__ 
uidoc = __revit__.ActiveUIDocument
doc = uidoc.Document

linked_doc = None
selection = uidoc.Selection.GetElementIds()
if selection.Count != 1:
    raise Exception("Please select one linked model instance.")

linked_instance = doc.GetElement(selection[0])
if not isinstance(linked_instance, DB.RevitLinkInstance):
    raise Exception("Selected element is not a Revit link instance.")

linked_doc = linked_instance.GetLinkDocument()
if linked_doc is None:
    raise Exception("Linked document could not be retrieved.")

linked_phases = linked_doc.Phases
current_phases = doc.Phases

current_phase_names = [p.Name for p in current_phases]
phase_map = {}

t = DB.Transaction(doc, "Copy Phases from Link")
t.Start()

try:
    for linked_phase in linked_phases:
        if linked_phase.Name not in current_phase_names:
            new_phase = DB.Phase.Create(doc)
            new_phase.Name = linked_phase.Name
            phase_map[linked_phase.Id] = new_phase.Id
        else:
            matching_phase = next(p for p in current_phases if p.Name == linked_phase.Name)
            phase_map[linked_phase.Id] = matching_phase.Id
    t.Commit()
except Exception:
    t.RollBack()
    print(traceback.format_exc())
