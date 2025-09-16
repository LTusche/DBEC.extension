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

# import clr
# clr.AddReference('System')
from System.Collections import Generic

from Autodesk.Revit import DB, UI
from Autodesk.Revit import Exceptions as rvtException
import traceback

from customWindow import InputBox, DialogResult
from pathfinder import pathfinder, Node

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
        return
    if not textInput:
        outputDialog.MainContent = "Keine Eingabe"
        outputDialog.Show()
        return

    loop = True
    selectionIds = Generic.List[DB.ElementId]([])
    while loop:
        try:
            reference = rvtSelection.PickObject(UI.Selection.ObjectType.Element)
            selectionIds.Add(reference.ElementId)
        except rvtException.OperationCanceledException as e:
            loop = False
        except Exception as e:
            loop = False
            print(e)

    
    if not selectionIds:
        # print("Keine Objekte ausgewählt")
        outputDialog.MainContent = "Keine Objekte ausgewählt"
        outputDialog.Show()
        return
    
    if len(selectionIds) > 1:
        fullPathNodes : list[Node] = []
        for index in range(len(selectionIds) - 1):
            elementOne = doc.GetElement(selectionIds[index])
            elementTwo = doc.GetElement(selectionIds[index+1])

            result = pathfinder(elementOne, elementTwo)
            if index == 0:
                fullPathNodes.extend(result.Nodes)
            else:
                fullPathNodes.extend(result.Nodes[1:])  # skip the first node to avoid duplicates
        
        if False:
            fullPathIds = Generic.List[DB.ElementId]([node.Id for node in fullPathNodes])
            rvtSelection.SetElementIds(fullPathIds)
            return

        preSelectionReferences = Generic.List[DB.Reference]([DB.Reference(node.Element) for node in fullPathNodes])
        selection_filter = CategorySelectionFilter(selectionfilter)
        try:
            references = rvtSelection.PickObjects(UI.Selection.ObjectType.Element, selection_filter, "Auswahl Bestätigen", preSelectionReferences)
        except rvtException.OperationCanceledException as e:
            return
        
        elements = [doc.GetElement(ref.ElementId) for ref in references]
    else:
        element = doc.GetElement(selectionIds[0])
        elements = [element]

    if False:
        dialog = UI.TaskDialog("Auswahl Bestätigen")
        dialog.TitleAutoPrefix = False
        dialog.MainInstruction = "Auswahl Bestätigen"
        dialog.MainContent = "Ist der Kabelweg so korrekt?"
        dialog.CommonButtons = UI.TaskDialogCommonButtons.Yes | UI.TaskDialogCommonButtons.No
        confirmDialogResult = dialog.Show()

        if confirmDialogResult != UI.TaskDialogResult.Yes:
            return
    

    transaction = DB.Transaction(doc, "Kabel Hinzufügen")
    transaction.Start()
    try:
        for element in elements:
            name_parameter = element.GetParameters("Kabel Name")[0]
            name_parameter_string = name_parameter.AsString()
            if name_parameter_string:
                cable_names = name_parameter_string.split("\n")
            else:
                cable_names = []
                
            cable_names.append(textInput)

            zipped = list(zip(cable_names))
            zipped.sort(key=lambda x: x[0])

            unzipped = list(zip(*zipped))
            sorted_cable_names = unzipped[0] if unzipped else []

            joined_names = "\n".join(sorted_cable_names)
            
            name_parameter.Set(joined_names)

    except:
        transaction.RollBack()
        print(traceback.format_exc())
        return
    
    transaction.Commit()

    if False:
        transaction = DB.Transaction(doc, "Kabel Hinzufügen")
        transaction.Start()
        try:
            for node in fullPathNodes:
                name_parameter = node.Element.GetParameters("Kabel Name")[0]
                name_parameter_string = name_parameter.AsString()
                if name_parameter_string:
                    cable_names = name_parameter_string.split("\n")
                else:
                    cable_names = []
                    
                cable_names.append(textInput)

                zipped = list(zip(cable_names))
                zipped.sort(key=lambda x: x[0])

                unzipped = list(zip(*zipped))
                sorted_cable_names = unzipped[0] if unzipped else []

                joined_names = "\n".join(sorted_cable_names)
                
                name_parameter.Set(joined_names)

        except:
            transaction.RollBack()
            print(traceback.format_exc())
            return
        
        transaction.Commit()
    
    return

    # Kabel in aktuelle Ansicht einfügen
    if result:
        selectionList = Generic.List[DB.ElementId](result.ElementIds)
        uidoc.Selection.SetElementIds(selectionList)
        
        # Create cable to distributor
        # Currently Revit cables are used, which are only available in the current 2D View
        ALLOWED_FLOORPLAN_VIEW_TYPES = [
            DB.ViewType.FloorPlan,
            DB.ViewType.CeilingPlan
        ]
        if doc.ActiveView.ViewType in ALLOWED_FLOORPLAN_VIEW_TYPES:
            #if len(result.Points) > 1:

            # if isinstance(result, updater.pathfinderResult):
            #     """
            #     pathToTray = self.MakePathOrthogonal([result.Points[0], point])
            #     result.Points.pop(0)
            #     for sPoint in pathToTray:
            #         result.Points.insert(0, sPoint)

            #     vtLocation = self.GetElementLocation(vtElement)
            #     pathToTray = self.MakePathOrthogonal([result.Points[-1], vtLocation])
            #     result.Points.pop(-1)
            #     for sPoint in pathToTray:
            #         result.Points.append(sPoint)
            #     """
                
            #     result.Points.insert(0, point)
            #     if result.Succeeded:
            #         result.Points.append(vtElement.Location.Point)
            
            transaction = DB.Transaction(doc, "Kabel erstellen")
            transaction.Start()
            try:   
                points = System.Collections.Generic.List[DB.XYZ](result.Points)

                for wireType in doc.Settings.ElectricalSetting.WireTypes:
                    wireTypeId = wireType.Id
                    break
                wire = DB.Electrical.Wire.Create(
                    doc,
                    wireTypeId,
                    HOST_APP.active_view.Id,
                    DB.Electrical.WiringType.Chamfer,
                    points,
                    None,
                    None
                )
                transaction.Commit()
            except:
                transaction.RollBack()
                print(traceback.format_exc())
                for point in result.Points:
                    print(point)


if __name__ == "__main__":
    try:
        mainfunc()
    except:
        print(traceback.format_exc())