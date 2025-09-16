from pyrevit import script
output = script.get_output()

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from Autodesk.Revit.UI import UIApplication
    __revit__ = UIApplication()


from Autodesk.Revit import DB, UI
from Autodesk.Revit import Exceptions as rvtException
import traceback

import clr
clr.AddReference('System')
from System.Collections import Generic

uiapp = __revit__
uidoc = __revit__.ActiveUIDocument
doc = uidoc.Document

nearbyCategories = Generic.List[DB.BuiltInCategory]([
    DB.BuiltInCategory.OST_CableTray,
    DB.BuiltInCategory.OST_CableTrayFitting,
    DB.BuiltInCategory.OST_ElectricalEquipment,
    DB.BuiltInCategory.OST_ElectricalFixtures])


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

def pathfinder(startElement, endElement, startpoint=None, endpoint=None, traySystemRequirement="SV") -> pathfinderResult:
    try:
        # A* Pathfinding algorithm
        debug = False
        startNode = Node(startElement)
        if startpoint:
            startNode.CenterXYZ = startpoint

        endNode = Node(endElement)
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
            
            # print(f"OpenNodes: {output.linkify([openNode.Id for openNode in open])}")
            open.pop(currentIndex)
            closed.append(currentNode)
            
            if debug:
                print("----NodeSeperator---------")
                print(f"CurrentNode: {output.linkify(currentNode.Id)}")
                if currentNode.Parent:
                    print(f"Parent: {output.linkify(currentNode.Parent.Id)}")
                # print(f"HCost: {currentNode.HCost} Distance to Goal")
                # print(f"GCost: {currentNode.GCost} Distance from Start")
                # print(f"FCost: {currentNode.FCost} Score")

            # Check if we found the end node
            if currentNode.Id == endNode.Id:
                currentNode.CenterXYZ = endNode.CenterXYZ
                # currentNode.XYZs = endNode.XYZs
                result = pathfinderResult(startNode, currentNode, True)
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
                    node = Node(doc.GetElement(connection.Owner.Id))
                    node.InXYZ = connection.Origin
                    # if not node.CenterXYZ.IsAlmostEqualTo(connector.Origin, 0.05):
                    #     currentNode.CenterXYZ = connector.Origin
                    #     #node.CenterXYZ = connector.Origin
                    connectedElements.append(node)
                if node:
                    continue

                # If currently a cable tray, require a non calbe tray to continue
                if isinstance(currentNode.Element, DB.Electrical.CableTray):
                    #nearbyElements = GetNearbyElements(connector.Origin, [DB.BuiltInCategory.OST_ElectricalEquipment])
                    nearbyElements = GetNearbyElements(connector.Origin, nearbyCategories)
                else:
                    nearbyElements = GetNearbyElements(connector.Origin, nearbyCategories)

                for nearbyElement in nearbyElements:
                    if nearbyElement.Id.IntegerValue == currentNode.Id.IntegerValue:
                        continue
                    # if currentNode.Parent:
                    #     if nearbyElement.Id.IntegerValue == currentNode.Parent.Id.IntegerValue:
                    #         continue
                    node = Node(nearbyElement)
                    node.AirGap = True
                    if isinstance(nearbyElement.Location, DB.LocationCurve):
                        intersectionResult = nearbyElement.Location.Curve.Project(connector.Origin)
                        node.InXYZ = intersectionResult.XYZPoint

                    # Ich kann nicht rausfinden wo das hier hin muss
                    # Aktuell wird der Luftweg von CenterXYZ zum eingang gerechnet
                    # Sollte aber vom Ausgang gerechnet werden
                    # if isinstance(currentNode.Element.Location, DB.LocationCurve):
                    #     currentNode.OutXYZ = connector.Origin
                    #     pass
                    connectedElements.append(node)

            
            if not connectedElements:
                nearbyElements = GetNearbyElements(currentNode.CenterXYZ, nearbyCategories)
                for nearbyElement in nearbyElements:
                    if nearbyElement.Id.IntegerValue == currentNode.Id.IntegerValue:
                        continue
                    # if currentNode.Parent: # Parent already excluded through closed nodes
                    #     if nearbyElement.Id.IntegerValue == currentNode.Parent.Id.IntegerValue:
                    #         continue
                    node = Node(nearbyElement)
                    node.AirGap = True
                    if isinstance(nearbyElement.Location, DB.LocationCurve):
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
                    if isinstance(currentNode.Element.Location, DB.LocationPoint) and node.InXYZ:
                        distance = node.InXYZ.DistanceTo(currentNode.CenterXYZ)
                        distance = DB.UnitUtils.ConvertFromInternalUnits(distance, DB.UnitTypeId.Meters)
                        penalty_threshold = 0.4
                        if distance > penalty_threshold:
                            distance = (distance - penalty_threshold) * 10 + penalty_threshold
                            # print("penalty applied")
                            # print(currentNode.Id.IntegerValue)
                            # print(f"gCost before penalty {gCost}")
                            gCost = DB.UnitUtils.ConvertToInternalUnits(distance, DB.UnitTypeId.Meters)
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
                            # print(f"Old Parent: {output.linkify(openNode.Parent.Id)}")
                            # print(f"New Parent: {output.linkify(node.Parent.Id)}")
                            #currentNode.Parent = openNode
                            node.parent = currentNode
                            
                #             stop = True
                # if stop: continue

                # Condition: Only allow trays of current system
                # if not trayAcceptsSystem(node.Element, traySystemRequirement):
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
        #print(script.get_output().linkify(currentBest.Element.Id))
        result = pathfinderResult(startNode, current, False)
        while current is not None:
            result.Insert(0,current)
            current = current.Parent
        print("Reached pathfinder end")
        return result
        #return "Ziel nicht im System? Versuche: " + str(c)

        
    except:
        print(traceback.format_exc())


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
        if isinstance(element.Location, DB.LocationCurve):
            self.CenterXYZ = element.Location.Curve.Evaluate(0.5,True)
        else:
            self.CenterXYZ = element.Location.Point

def GetNearbyElements(point, categories, radiusmm = 1000):
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

        minPoint = DB.XYZ(point.X - radius, point.Y - radius, point.Z - radius)
        maxPoint = DB.XYZ(point.X + radius, point.Y + radius, point.Z + radius)
        outline = DB.Outline(minPoint, maxPoint)

        if isinstance(categories, list):
            categories = Generic.List[DB.BuiltInCategory](categories)
        elif isinstance(categories, DB.BuiltInCategory):
            categories = Generic.List[DB.BuiltInCategory]([categories])

        collector = DB.FilteredElementCollector(doc)
        collector.WhereElementIsNotElementType()
        collector.WherePasses(DB.ElementMulticategoryFilter(categories)) 
        collector.WherePasses(DB.BoundingBoxIntersectsFilter(outline))

        elements = collector.ToElements()

        if elements:
            return elements
        else:
            return []
        
        # bbox = element.Geometry[options].GetBoundingBox()
        # minPoint = DB.XYZ(bbox.Min.X, bbox.Min.Y, bbox.Min.Z)
        # maxPoint = DB.XYZ(bbox.Max.X, bbox.Max.Y, bbox.Max.Z)
        # outline = DB.Outline(minPoint, maxPoint)
        # clashCollector.WherePasses(DB.BoundingBoxIntersectsFilter(outline))
    except:
        print(traceback.format_exc())