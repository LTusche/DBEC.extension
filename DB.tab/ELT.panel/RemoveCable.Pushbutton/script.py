# -*- coding=utf-8 -*-

# print("Version")
# import sys
# print(sys.version)

# from pyrevit import script
# output = script.get_output()

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from Autodesk.Revit.UI import UIApplication
    __revit__ = UIApplication()

import clr
clr.AddReference('System')
from System.Collections import Generic

from Autodesk.Revit import DB, UI
from Autodesk.Revit import Exceptions as rvtException
import traceback

from customWindow import InputBox, DialogResult

# Idee: Linie zeichnen um Pfad vorzugeben,
# Pfad auf naheliegende Elemente projezieren

filterCategories = Generic.List[DB.BuiltInCategory]([
    DB.BuiltInCategory.OST_CableTray,
    DB.BuiltInCategory.OST_CableTrayFitting,
    DB.BuiltInCategory.OST_ElectricalEquipment,
    DB.BuiltInCategory.OST_ElectricalFixtures])

selectionfilter = DB.ElementMulticategoryFilter(filterCategories)

class CategorySelectionFilter(UI.Selection.ISelectionFilter):
    def __init__(self, selectionfilter):
        self.selectionfilter = selectionfilter

    def AllowElement(self, element):
        return self.selectionfilter.PassesFilter(element)
        #return element.Category is not None and element.Category.Id.IntegerValue in [int(cat) for cat in self.categories]

    def AllowReference(self, reference, point):
        return True

def get_elements_with_parameter_containing(doc, parameter_name, value_to_find):
    # Get a sample element to determine the parameter ID
    sample_collector = DB.FilteredElementCollector(doc).WhereElementIsNotElementType()
    sample_collector.WherePasses(selectionfilter)
    sample_element = sample_collector.FirstElement()
    
    if sample_element is None:
        return "No element Found"
    
    param = sample_element.LookupParameter(parameter_name)
    if param is None:
        return "Parameter not found"

    param_id = param.Id

    # Create a FilterStringRule for the "contains" condition
    string_rule = DB.ParameterFilterRuleFactory.CreateContainsRule(
        param_id,
        value_to_find,
        False  # caseSensitive
    )

    # Wrap in an ElementParameterFilter
    param_filter = DB.ElementParameterFilter(string_rule)

    # Apply filter to all elements (excluding element types)
    collector = DB.FilteredElementCollector(doc).WhereElementIsNotElementType()
    collector.WherePasses(selectionfilter)
    collector.WherePasses(param_filter)

    return collector.ToElements()

def mainfunc():
    uiapp = __revit__
    uidoc = __revit__.ActiveUIDocument
    doc = uidoc.Document

    activeView = uidoc.ActiveView
    rvtSelection = uidoc.Selection

    outputDialog = UI.TaskDialog("Kabel Hinzufügen")
    outputDialog.TitleAutoPrefix = False
    outputDialog.CommonButtons = UI.TaskDialogCommonButtons.Ok


    form = InputBox()
    inputResult = form.ShowDialog()

    textInput = form.textbox.Text

    if inputResult != DialogResult.OK:
        # print("Vorgang Abgebrochen")
        # outputDialog.MainContent = "Vorgang Abgebrochen"
        # outputDialog.Show()
        return
    if not textInput:
        # print("Keine Eingabe")
        outputDialog.MainContent = "Keine Eingabe"
        outputDialog.Show()
        return

    
    #elements = get_elements_with_parameter_containing(doc, "Kabel Name", textInput)

    selection_filter = CategorySelectionFilter(selectionfilter)

    try:
        references = rvtSelection.PickObjects(UI.Selection.ObjectType.Element, selection_filter)
    except rvtException.OperationCanceledException as e:
        return

    elements = [doc.GetElement(ref.ElementId) for ref in references]
    
    transaction = DB.Transaction(doc, "Kabel Hinzufügen")
    transaction.Start()
    try:
        for element in elements:
            name_parameter = element.LookupParameter("Kabel Name")
            name_parameter_string = name_parameter.AsString()
            if name_parameter_string:
                cable_names = name_parameter_string.split("\n")
            else:
                cable_names = []
                
            if textInput not in cable_names:
                continue

            cable_names.remove(textInput)

            # zipped = list(zip(cable_names))
            # zipped.sort(key=lambda x: x[0])

            # unzipped = list(zip(*zipped))
            # sorted_cable_names = unzipped[0] if unzipped else []

            joined_names = "\n".join(cable_names)
            
            name_parameter.Set(joined_names)

    except:
        transaction.RollBack()
        print(traceback.format_exc())
        return
    
    transaction.Commit()
    #print("Done")


if __name__ == "__main__":
    try:
        mainfunc()
    except:
        print(traceback.format_exc())