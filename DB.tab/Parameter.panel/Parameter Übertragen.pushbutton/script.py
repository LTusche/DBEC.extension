# -*- coding=utf-8 -*-
# import math

from pyrevit import forms, revit, DB, UI
from Autodesk.Revit import Exceptions

uidoc = revit.uidoc
doc = revit.doc

def get_selected_linked_element():
    """Prompt user to select a linked element."""
    
    try:
        ref = uidoc.Selection.PickObject(UI.Selection.ObjectType.LinkedElement, "Select a linked element")
        link_instance = doc.GetElement(ref.ElementId)
        
        if isinstance(link_instance, DB.RevitLinkInstance):
            linked_doc = link_instance.GetLinkDocument()
            linked_elem = linked_doc.GetElement(ref.LinkedElementId)
            return linked_elem, linked_doc
    except:
        forms.alert("Auswahl wurde abgebrochen.")
        return None, None
    
    forms.alert("Selected element is not from a linked model.")
    return None, None

def get_selected_active_elements():
    """Prompt user to select elements in the active document."""
    references = uidoc.Selection.PickObjects(UI.Selection.ObjectType.Element,"Select target elements in the active document")
    elements = [doc.GetElement(reference.ElementId) for reference in references]
    if not elements:
        forms.alert("Keine Elemente ausgewählt")
    return elements

def transfer_parameters(source_elem, target_elems, param_defs):
    """Transfer specified parameters from source to targets."""
    if not source_elem or not target_elems:
        return
    
    with revit.Transaction("Parameter Übertragen"):
        param_names = [p[0] for p in param_defs]

        for param_name in param_names:
            escape_param = None
            for target_elem in target_elems:
                for source_param in source_elem.GetParameters(param_name):
                    if not source_param.HasValue: continue
                    target_params = target_elem.GetParameters(param_name)
                    if target_params.Count < 1:
                        escape_param = forms.select_parameters(target_elem, 
                                                include_type=False,
                                                multiple=False,
                                                title="Kein gültiger Zielparameter für {target_param} gefunden, bitte Ersatz auswählen")
                        if not escape_param: raise Exception("Keine Auswahl")
                        param_name = escape_param[0][0]
                    for target_param in target_elem.GetParameters(param_name):
                        if source_param.StorageType == DB.StorageType.Integer:
                            target_param.Set(source_param.AsInteger())
                        elif source_param.StorageType == DB.StorageType.Double:
                            target_param.Set(source_param.AsDouble())
                        elif source_param.StorageType == DB.StorageType.String:
                            target_param.Set(source_param.AsString())
                        else: continue
                    break

        # for target in target_elems:
        #     for param_name in param_names:
        #         source_param = source_elem.LookupParameter(param_name)
        #         target_param = target.LookupParameter(param_name)
                
        #         if source_param and target_param and not target_param.IsReadOnly:
        #             target_param.Set(source_param.AsValueString() if source_param.StorageType == DB.StorageType.String else source_param.AsDouble())
                
    forms.alert("Parameter erfolgreich Übertragen.")

def main():
    try:
        linked_elem, linked_doc = get_selected_linked_element()
        if not linked_elem:
            return
        
        paramdefs = forms.select_parameters(linked_elem, include_type=False)
        if not paramdefs:
            forms.alert("Keine Parameter ausgewählt, befehl wird abgebrochen.")
            return

        target_elems = get_selected_active_elements()
        if not target_elems:
            return
    except Exceptions.OperationCanceledException:
        return
    
    
    
    transfer_parameters(linked_elem, target_elems, paramdefs)

if __name__ == "__main__":
    main()
