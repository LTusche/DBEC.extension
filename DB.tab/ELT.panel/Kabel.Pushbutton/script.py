# -*- coding=utf-8 -*-

# print("Version")
# import sys
# print(sys.version)

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from Autodesk.Revit.UI import UIApplication
    __revit__ = UIApplication()

from pyrevit import DB, UI, HOST_APP
from pyrevit import framework, script, forms
from pyrevit.framework import System
import math
import traceback
import json
import time
from functools import wraps
from collections import OrderedDict



class Updater(DB.IUpdater):
    def __init__(self, addin_id):
        self.traceback = traceback
        self.System = System
        self.DB = DB
        self.UI = UI
        #self.script = script
        self.output = script.get_output()

        self.uiuiapp = __revit__
        self.uidoc = __revit__.ActiveUIDocument
        self.doc = uidoc.Document

        self.nearbyCategories = self.System.Collections.Generic.List[self.DB.BuiltInCategory]([
            self.DB.BuiltInCategory.OST_CableTray,
            self.DB.BuiltInCategory.OST_CableTrayFitting,
            self.DB.BuiltInCategory.OST_ElectricalEquipment])

    def Execute(self, data):
        self.uiuiapp = __revit__
        self.uidoc = __revit__.ActiveUIDocument
        self.doc = uidoc.Document
        pass

    def GetNearbyElements(self, point, categories, radiusmm = 1000):
        try:
            if not categories:
                return []
            radius = DB.UnitUtils.ConvertToInternalUnits(radiusmm, DB.UnitTypeId.Millimeters)
            # sphere = self.CreateSphere(point, radiusmm / 304.8)

            # typed_list = self.System.Collections.Generic.List[self.DB.BuiltInCategory]([
            #     self.DB.BuiltInCategory.OST_CableTray,
            #     self.DB.BuiltInCategory.OST_CableTrayFitting])
            # catFilter = self.DB.ElementMulticategoryFilter(typed_list)

            # collector = self.DB.FilteredElementCollector(doc)
            # collector.WherePasses(catFilter)
            # collector.WhereElementIsNotElementType()
            # collector.WherePasses(self.DB.ElementIntersectsSolidFilter(sphere))

            minPoint = self.DB.XYZ(point.X - radius, point.Y - radius, point.Z - radius)
            maxPoint = self.DB.XYZ(point.X + radius, point.Y + radius, point.Z + radius)
            outline = self.DB.Outline(minPoint, maxPoint)

            if isinstance(categories, list):
                categories = self.System.Collections.Generic.List[self.DB.BuiltInCategory](categories)
            elif isinstance(categories, DB.BuiltInCategory):
                categories = self.System.Collections.Generic.List[self.DB.BuiltInCategory]([categories])

            collector = DB.FilteredElementCollector(self.doc)
            collector.WhereElementIsNotElementType()
            collector.WherePasses(self.DB.ElementMulticategoryFilter(categories)) 
            collector.WherePasses(self.DB.BoundingBoxIntersectsFilter(outline))

            elements = collector.ToElements()

            if elements:
                return elements
            else:
                return []
            
            # bbox = element.Geometry[options].GetBoundingBox()
            # minPoint = self.DB.XYZ(bbox.Min.X, bbox.Min.Y, bbox.Min.Z)
            # maxPoint = self.DB.XYZ(bbox.Max.X, bbox.Max.Y, bbox.Max.Z)
            # outline = self.DB.Outline(minPoint, maxPoint)
            # clashCollector.WherePasses(self.DB.BoundingBoxIntersectsFilter(outline))
        except:
            print(self.traceback.format_exc())

    def pathfinder(self, startElement, endElement, startpoint=None, endpoint=None, traySystemRequirement="SV"):
        try:
            debug = False
            # A* Pathfinding algorithm
            startNode = self.Node(startElement)
            if startpoint:
                startNode.CenterXYZ = startpoint

            endNode = self.Node(endElement)
            if startpoint:
                endNode.CenterXYZ = endpoint
            
            open = [startNode]
            closed = []
            
            c = 0
            while len(open) > 0 and c < 1000 :
                currentNode = open[0]
                currentIndex = 0
                
                for index, item in enumerate(open):
                    if item.FCost < currentNode.FCost:
                        currentNode = item
                        currentIndex = index
                
                # print(f"OpenNodes: {self.output.linkify([openNode.Id for openNode in open])}")
                open.pop(currentIndex)
                closed.append(currentNode)
                
                if debug:
                    print("----NodeSeperator---------")
                    print(f"CurrentNode: {self.output.linkify(currentNode.Id)}")
                    if currentNode.Parent:
                        print(f"Parent: {self.output.linkify(currentNode.Parent.Id)}")
                    # print(f"HCost: {currentNode.HCost} Distance to Goal")
                    # print(f"GCost: {currentNode.GCost} Distance from Start")
                    # print(f"FCost: {currentNode.FCost} Score")

                # Check if we found the end node
                if currentNode.Id == endNode.Id:
                    currentNode.CenterXYZ = endNode.CenterXYZ
                    # currentNode.XYZs = endNode.XYZs
                    result = self.pathfinderResult(startNode, currentNode, True)
                    current = currentNode
                    while current is not None:
                        result.Insert(0,current)
                        current = current.Parent
                    return result
                
                # Find Connected Nodes
                # if hasattr(currentNode.Element, "MEPModel"):
                #     connectors = currentNode.Element.MEPModel.ConnectorManager.Connectors
                # elif hasattr(currentNode.Element, "ConnectorManager"):
                #     connectors = currentNode.Element.ConnectorManager.Connectors
                # else:
                #     connectors=[]
                
                try:
                    connectors = currentNode.Element.MEPModel.ConnectorManager.Connectors
                except:
                    try:
                        connectors = currentNode.Element.ConnectorManager.Connectors
                    except:			
                        connectors = []
                
                if debug:
                    print(f"Has Connectors: {bool(connectors)}")

                node = None
                connectedElements = []
                for connector in connectors:
                    node = None
                    for connection in connector.AllRefs:
                        if connection.Owner.Id == connector.Owner.Id:
                            continue
                        node = self.Node(self.doc.GetElement(connection.Owner.Id))
                        node.InXYZ = connection.Origin
                        # if not node.CenterXYZ.IsAlmostEqualTo(connector.Origin, 0.05):
                        #     currentNode.CenterXYZ = connector.Origin
                        #     #node.CenterXYZ = connector.Origin
                        connectedElements.append(node)
                    if node:
                        continue

                    # If currently a cable tray, require a non calbe tray to continue
                    if isinstance(currentNode.Element, self.DB.Electrical.CableTray):
                        #nearbyElements = self.GetNearbyElements(connector.Origin, [self.DB.BuiltInCategory.OST_ElectricalEquipment])
                        nearbyElements = self.GetNearbyElements(connector.Origin, self.nearbyCategories)
                    else:
                        nearbyElements = self.GetNearbyElements(connector.Origin, self.nearbyCategories)

                    for nearbyElement in nearbyElements:
                        if nearbyElement.Id.IntegerValue == currentNode.Id.IntegerValue:
                            continue
                        # if currentNode.Parent:
                        #     if nearbyElement.Id.IntegerValue == currentNode.Parent.Id.IntegerValue:
                        #         continue
                        node = self.Node(nearbyElement)
                        node.AirGap = True
                        if isinstance(nearbyElement.Location, self.DB.LocationCurve):
                            intersectionResult = nearbyElement.Location.Curve.Project(connector.Origin)
                            node.InXYZ = intersectionResult.XYZPoint

                        # Ich kann nicht rausfinden wo das hier hin muss
                        # Aktuell wird der Luftweg von CenterXYZ zum eingang gerechnet
                        # Sollte aber vom Ausgang gerechnet werden
                        # if isinstance(currentNode.Element.Location, self.DB.LocationCurve):
                        #     currentNode.OutXYZ = connector.Origin
                        #     pass
                        connectedElements.append(node)

                
                if not connectedElements:
                    nearbyElements = self.GetNearbyElements(currentNode.CenterXYZ, self.nearbyCategories)
                    for nearbyElement in nearbyElements:
                        if nearbyElement.Id.IntegerValue == currentNode.Id.IntegerValue:
                            continue
                        # if currentNode.Parent: # Parent already excluded through closed nodes
                        #     if nearbyElement.Id.IntegerValue == currentNode.Parent.Id.IntegerValue:
                        #         continue
                        node = self.Node(nearbyElement)
                        node.AirGap = True
                        if isinstance(nearbyElement.Location, self.DB.LocationCurve):
                            intersectionResult = nearbyElement.Location.Curve.Project(currentNode.CenterXYZ)
                            node.InXYZ = intersectionResult.XYZPoint
                        connectedElements.append(node)

                # Loop through adjecent nodes
                for node in connectedElements:
                
                    node.Parent = currentNode
                    stop = False
                    
                    # Condition: Node already processed
                    for closedNode in closed[:]:
                        if node.Id == closedNode.Id:
                            stop = True
                    if stop: continue

                    hCost = node.CenterXYZ.DistanceTo(endNode.CenterXYZ)
                    node.HCost = hCost # Distance to Goal
                    gCost = node.CenterXYZ.DistanceTo(currentNode.CenterXYZ)
                    if node.AirGap:
                        if isinstance(currentNode.Element.Location, self.DB.LocationPoint) and node.InXYZ:
                            distance = node.InXYZ.DistanceTo(currentNode.CenterXYZ)
                            distance = self.DB.UnitUtils.ConvertFromInternalUnits(distance, self.DB.UnitTypeId.Meters)
                            penalty_threshold = 0.4
                            if distance > penalty_threshold:
                                distance = (distance - penalty_threshold) * 10 + penalty_threshold
                                # print("penalty applied")
                                # print(currentNode.Id.IntegerValue)
                                # print(f"gCost before penalty {gCost}")
                                gCost = self.DB.UnitUtils.ConvertToInternalUnits(distance, self.DB.UnitTypeId.Meters)
                                # print(f"gCost after penalty {gCost}")
                        # if node.InXYZ and currentNode.OutXYZ:
                        #     gCost = node.InXYZ.DistanceTo(currentNode.OutXYZ) * 10
                        # elif node.InXYZ:
                        #     gCost = node.InXYZ.DistanceTo(currentNode.CenterXYZ) * 10
                        # elif currentNode.OutXYZ:
                        #     gCost = node.CenterXYZ.DistanceTo(currentNode.OutXYZ) * 10

                    node.GCost = gCost + currentNode.GCost # Distance from Start
                    node.FCost = node.GCost + hCost # GCost + HCost

                    # Condition: Node already open
                    for openNode in open[:]:
                        if node.Id == openNode.Id:
                            #if node.GCost < currentNode.GCost:
                            if openNode.GCost > node.GCost:
                                #currentNode.Parent.Parent = currentNode
                                # print(f"Node already exists and new GCost ist better")
                                # print(f"Old Parent: {self.output.linkify(openNode.Parent.Id)}")
                                # print(f"New Parent: {self.output.linkify(node.Parent.Id)}")
                                #currentNode.Parent = openNode
                                node.parent = currentNode
                                
                    #             stop = True
                    # if stop: continue

                    # Condition: Only allow trays of current system
                    # if not self.trayAcceptsSystem(node.Element, traySystemRequirement):
                    #     continue

                    # traySystems = set()
                    # instanceParameter = list(node.Element.GetParameters("TGA_VT-Systeme-Ergänzung"))
                    # typeParameter = list(node.Element.GetParameters("TGA_VT-Systeme"))
                    # for parameter in instanceParameter + typeParameter:
                    #     pvalue = parameter.AsString()
                    #     if pvalue is None or pvalue == "":
                    #         continue
                    #     for s in pvalue.split(";"):
                    #         traySystems.add(s.strip())
                    # if len(traySystems) == 0:
                    #     traySystems.add("AV")
                    # if traySystemRequirement not in traySystems:
                    #     continue
                    # node.XYZs.insert(0, currentNode.XYZs[-1])
                    
                    open.append(node)
                
                c += 1

            currentBest = closed[-1]
            for closedNode in closed:
                if closedNode.HCost < currentBest.HCost and closedNode.HCost != 0:
                    currentBest = closedNode
            current = currentBest
            #print(currentBest.Element.Id)
            #print(self.script.get_output().linkify(currentBest.Element.Id))
            result = self.pathfinderResult(startNode, current, False)
            while current is not None:
                result.Insert(0,current)
                current = current.Parent
            print("Reached pathfinder end")
            return result
            #return "Ziel nicht im System? Versuche: " + str(c)

            
        except:
            print(self.traceback.format_exc())

    def CreateSphere(self, center, radius):
        frame = self.DB.Frame(center, self.DB.XYZ.BasisX, self.DB.XYZ.BasisY, self.DB.XYZ.BasisZ)

        arc = self.DB.Arc.Create(
            center - radius * self.DB.XYZ.BasisZ,
            center + radius * self.DB.XYZ.BasisZ,
            center + radius * self.DB.XYZ.BasisX)

        line = self.DB.Line.CreateBound(arc.GetEndPoint(1),arc.GetEndPoint(0))

        halfCircle = self.DB.CurveLoop()
        halfCircle.Append(arc)
        halfCircle.Append(line)

        loops = self.System.Collections.Generic.List[self.DB.CurveLoop]()
        loops.Add(halfCircle)

        sphere = self.DB.GeometryCreationUtilities.CreateRevolvedGeometry(frame, loops, 0, 2 * self.math.pi)

        return sphere

    class pathfinderResult():
        def __init__(self, StartNode = None, EndNode = None, Succeeded = None, Nodes = []):
            self.Succeeded = Succeeded
            self.Nodes = Nodes
            self.Elements = []
            self.ElementIds = []
            self.ElementIntegerIds = []
            self.Points = []
            self.StartNode = StartNode
            self.EndNode = EndNode
            if Succeeded:
                self.Length = EndNode.GCost
            else:
                self.Length = float("inf")

        def Add(self, node):
            self.Nodes.append(node)
            self.Elements.append(node.Element)
            self.Points.append(node.CenterXYZ)
            self.ElementIds.append(node.Id)
            self.ElementIntegerIds.append(node.Id.IntegerValue)

        def Insert(self, index, node):
            self.Nodes.insert(index, node)
            self.Elements.insert(index, node.Element)
            if node.OutXYZ:
                self.Points.insert(index, node.OutXYZ)
            if node.CenterXYZ:
                self.Points.insert(index, node.CenterXYZ)
            if node.InXYZ:
                self.Points.insert(index, node.InXYZ)
            self.ElementIds.insert(index, node.Id)
            self.ElementIntegerIds.insert(index, node.Id.IntegerValue)

    class freeStyleResult():
        def __init__(self, StartPoint = None, EndPoint = None, Succeeded = None):
            self.StartPoint = StartPoint
            self.EndPoint = EndPoint
            self.Points = [StartPoint, EndPoint]
            self.Succeeded = Succeeded
            self.Length = float("inf")
            self.ElementIntegerIds = []
            self.ElementIds = []
            self.Elements = []

    class Node():
        def __init__(self, element):
            self.Element = element
            self.Id = element.Id
            self.Parent = None
            self.FCost = 0 # GCost + HCost
            self.GCost = 0 # Distance from Start
            self.HCost = 0 # Distance to Goal
            self.CenterXYZ = None
            self.InXYZ = None
            self.OutXYZ = None
            self.AirGap = False
            self.DB = DB
            if isinstance(element.Location, self.DB.LocationCurve):
                self.CenterXYZ = element.Location.Curve.Evaluate(0.5,True)
            else:
                self.CenterXYZ = element.Location.Point
            # try:
            #     self.XYZ = element.Location.Curve.Evaluate(0.5,True)
            # except:
            #     self.XYZ = element.Location.Point
    
    def GetUpdaterId(self):
        return self.id

    def GetUpdaterName(self):
        return "Kabelsystem Updater"

    def GetAdditionalInformation(self):
        return u"Führt das Kabelsystem im hintergrund mit."

    def GetChangePriority(self):
        return DB.ChangePriority.MEPFixtures

if __name__ == "__main__":
    uiapp = __revit__
    uidoc = __revit__.ActiveUIDocument
    doc = uidoc.Document

    activeView = uidoc.ActiveView
    rvtSelection = uidoc.Selection

    startRef = None
    endRef = None
    try:
        startRef = uidoc.Selection.PickObject(UI.Selection.ObjectType.Element)
        endRef = uidoc.Selection.PickObject(UI.Selection.ObjectType.Element)
    except:
        pass
    if startRef and endRef:
        startElement = doc.GetElement(startRef.ElementId)
        endElement = doc.GetElement(endRef.ElementId)

        updater = Updater(HOST_APP.addin_id)

        result = updater.pathfinder(startElement, endElement)
        if result:
            selectionList = System.Collections.Generic.List[DB.ElementId](result.ElementIds)
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
        

    # Create extensible storage
    # schemaBuilder = DB.ExtensibleStorage.SchemaBuilder(System.Guid("f497c419-4958-48f0-85da-a99771aa0ff4"))
    # schemaBuilder.SetReadAccessLevel(DB.ExtensibleStorage.AccessLevel.Public)
    # schemaBuilder.SetWriteAccessLevel(DB.ExtensibleStorage.AccessLevel.Public)
    # schemaBuilder.SetVendorId("DB")
    # schemaBuilder.SetSchemaName("TestSchema")
    # fieldBuilder = schemaBuilder.AddSimpleField("TestElementId", DB.ElementId)
    # fieldBuilder.SetDocumentation


def __selfinit__(script_cmp, ui_button_cmp, __rvt__):
    pass