# from pyrevit import script
# output = script.get_output()

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

class Node():
    def __init__(self, element:DB.Element):
        self.Element : DB.Element = element
        self.Id : DB.ElementId = element.Id
        self.Parent : Node = None
        self.FCost = 0 # GCost + HCost
        self.GCost = 0 # Distance from Start
        self.HCost = 0 # Distance to Goal
        self.CenterXYZ : DB.XYZ = None
        self.InXYZ : DB.XYZ = None
        self.ParentOutXYZ : DB.XYZ = None
        self.AirGap = False
        self.DB = DB
        if isinstance(element.Location, DB.LocationCurve):
            self.CenterXYZ = element.Location.Curve.Evaluate(0.5,True)
        else:
            self.CenterXYZ = element.Location.Point

class pathfinderResult():
    def __init__(self, StartNode = None, EndNode = None, Succeeded = None, Nodes = None):
        self.Succeeded = Succeeded
        self.Nodes: list[Node] = Nodes if Nodes is not None else []
        self.Elements : list[DB.Element] = []
        self.ElementIds : list[DB.ElementId] = []
        self.ElementIntegerIds : list[int] = []
        self.Points : list[DB.XYZ] = []
        self.StartNode : Node = StartNode
        self.EndNode : Node = EndNode
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

    def Insert(self, index, node:Node):
        self.Nodes.insert(index, node)
        self.Elements.insert(index, node.Element)
        if node.CenterXYZ:
            self.Points.insert(index, node.CenterXYZ)
        if node.InXYZ:
            self.Points.insert(index, node.InXYZ)
        if node.ParentOutXYZ:
            self.Points.insert(index, node.ParentOutXYZ)
        self.ElementIds.insert(index, node.Id)
        self.ElementIntegerIds.insert(index, node.Id.IntegerValue)

def pathfinder(startElement, endElement, startpoint=None, endpoint=None, traySystemRequirement="SV") -> pathfinderResult:
    try:
        # A* Pathfinding algorithm
        startNode = Node(startElement)
        if startpoint:
            startNode.CenterXYZ = startpoint

        endNode = Node(endElement)
        if endpoint:
            endNode.CenterXYZ = endpoint
        
        open : list[Node] = [startNode]
        closed : list[Node] = []
        
        c = 0
        while len(open) > 0 and c < 1000 :
            currentNode = open[0]
            currentIndex = 0
            
            for index, item in enumerate(open):
                if item.FCost < currentNode.FCost:
                    currentNode = item
                    currentIndex = index
                    
            # print("------------")
            # print(f"CurrentNode: {output.linkify(currentNode.Id)} fcost: {currentNode.FCost}")
            # if currentNode.Parent:
                # print(f"CurrentNode Parent: {output.linkify(currentNode.Parent.Id)} fcost: {currentNode.FCost}")
            # print(f"fcost: {currentNode.FCost}")
            
            # print(f"OpenNodes: {output.linkify([openNode.Id for openNode in open])}")
            open.pop(currentIndex)
            closed.append(currentNode)

            # print("open nodes:")
            # print(output.linkify([openNode.Id for openNode in open]))
            
            # Check if we found the end node
            if currentNode.Id == endNode.Id:
                currentNode.CenterXYZ = endNode.CenterXYZ
                result = pathfinderResult(startNode, currentNode, True)
                current = currentNode
                while current is not None:
                    result.Insert(0,current)
                    current = current.Parent
                return result
            
            try:
                connectors = currentNode.Element.MEPModel.ConnectorManager.Connectors
            except:
                try:
                    connectors = currentNode.Element.ConnectorManager.Connectors
                except:			
                    connectors = []

            node = None
            connectedElements : list[Node] = []
            for connector in connectors:
                # print(f"ConnectorOrigin: {connector.Origin}")
                node = None
                for connection in connector.AllRefs:
                    if connection.Owner.Id == connector.Owner.Id:
                        continue
                    node = Node(doc.GetElement(connection.Owner.Id))
                    node.InXYZ = connection.Origin
                    #node.ParentOutXYZ = connector.Origin
                    connectedElements.append(node)
                if node:
                    continue

                # If currently a cable tray, require a non cable tray to continue
                # if isinstance(currentNode.Element, DB.Electrical.CableTray):
                #     nearbyElements = GetNearbyElements(connector.Origin, nearbyCategories)
                # else:
                nearbyElements = GetNearbyElements(connector.Origin, nearbyCategories)

                for nearbyElement in nearbyElements:
                    if nearbyElement.Id.IntegerValue == currentNode.Id.IntegerValue:
                        continue
                    # print(f"NearbyElement: {output.linkify(nearbyElement.Id)}")
                    node = Node(nearbyElement)
                    node.CenterXYZ = DB.XYZ(node.CenterXYZ.X, node.CenterXYZ.Y, connector.Origin.Z)
                    node.AirGap = True
                    if isinstance(nearbyElement.Location, DB.LocationCurve):
                        # print(f"NearbyElement {output.linkify(nearbyElement.Id)} is a curve")
                        intersectionResult = nearbyElement.Location.Curve.Project(connector.Origin)
                        # print("connector.Origin projected to nearbyElement Curve")
                        node.InXYZ = intersectionResult.XYZPoint
                        # print(f"nearbyElement node.InXYZ set to {intersectionResult.XYZPoint}")
                    # if isinstance(currentNode.Element.Location, DB.LocationCurve):
                    #     # print(f"CurrentNode {output.linkify(currentNode.Id)} is a curve")
                    #     if node.InXYZ:
                    #         intersectionResult = currentNode.Element.Location.Curve.Project(node.InXYZ)
                    #         # print("nearbyElement node.InXYZ projected to CurrentNode Curve")
                    #     else:
                    #         intersectionResult = currentNode.Element.Location.Curve.Project(node.CenterXYZ)
                    #         # print("nearbyElement node.CenterXYZ projected to CurrentNode Curve")
                    #     node.ParentOutXYZ = intersectionResult.XYZPoint
                    #     # print(f"node.ParentOutXYZ set to {intersectionResult.XYZPoint}")
                    node.ParentOutXYZ = connector.Origin

                    connectedElements.append(node)

            
            if not connectedElements:
                nearbyElements = GetNearbyElements(currentNode.CenterXYZ, nearbyCategories)
                for nearbyElement in nearbyElements:
                    if nearbyElement.Id.IntegerValue == currentNode.Id.IntegerValue:
                        continue
                    # if currentNode.Parent: # Parent already excluded through closed nodes
                    #     if nearbyElement.Id.IntegerValue == currentNode.Parent.Id.IntegerValue:
                    #         continue
                    # print(f"NearbyElement: {output.linkify(nearbyElement.Id)}")
                    node = Node(nearbyElement)
                    node.AirGap = True
                    if isinstance(nearbyElement.Location, DB.LocationCurve):
                        # print("nearbyElement is a curve")
                        # print("node.InXYZ set to NearbyElement.Curve(CurrentNode.CenterXYZ) projection")
                        intersectionResult = nearbyElement.Location.Curve.Project(currentNode.CenterXYZ)
                        node.InXYZ = intersectionResult.XYZPoint
                    if isinstance(currentNode.Element.Location, DB.LocationCurve):
                        # print("Current Node is a curve")
                        if node.InXYZ:
                            intersectionResult = currentNode.Element.Location.Curve.Project(node.InXYZ)
                            # print("node.ParentOutXYZ set to NearbyElement Curve projection")
                        else:
                            intersectionResult = currentNode.Element.Location.Curve.Project(node.CenterXYZ)
                            # print("node.ParentOutXYZ set to NearbyElement CenterXYZ projection")
                        node.ParentOutXYZ = intersectionResult.XYZPoint

                    connectedElements.append(node)


            # print("Connected Nodes:")
            newOpenNodes = []
            # Loop through adjecent nodes
            for node in connectedElements:
            
                node.Parent = currentNode
                stop = False
                
                # Condition: Node already processed
                for closedNode in closed[:]:
                    if node.Id == closedNode.Id:
                        stop = True
                if stop: continue

                # print(f"ConnectedNode: {output.linkify(node.Element.Id)}")

                internal_hCost = node.CenterXYZ.DistanceTo(endNode.CenterXYZ)
                hCost = DB.UnitUtils.ConvertFromInternalUnits(internal_hCost, DB.UnitTypeId.Meters)
                node.HCost = hCost # Distance to Goal

                if node.InXYZ:
                    inXYZ = node.InXYZ
                    # print(f"Node is a curve InXYZ: {inXYZ}")
                else:
                    inXYZ = node.CenterXYZ
                    # print(f"Node is not a curve CenterXYZ {inXYZ}")

                if node.ParentOutXYZ:
                    outXYZ = node.ParentOutXYZ
                    # print(f"Parent is a curve InXYZ{outXYZ}")
                else:
                    outXYZ = currentNode.CenterXYZ
                    # print(f"Parent is not a curve CenterXYZ{outXYZ}")
                
                #DB.UnitUtils.ConvertFromInternalUnits(
                #, DB.UnitTypeId.Meters)

                internal_gCost = inXYZ.DistanceTo(outXYZ)
                gCost = DB.UnitUtils.ConvertFromInternalUnits(internal_gCost, DB.UnitTypeId.Meters)

                # print(f"initial gCost: {gCost}")

                if node.AirGap: # Add penalty for air gap
                    #distance = DB.UnitUtils.ConvertFromInternalUnits(gCost, DB.UnitTypeId.Meters)
                    distance = gCost
                    penalty_threshold = 0.600
                    if distance > penalty_threshold:
                        newDistance = ((distance - penalty_threshold) * 10) + penalty_threshold
                        #gCost = DB.UnitUtils.ConvertToInternalUnits(newDistance, DB.UnitTypeId.Meters)
                        gCost = newDistance

                # print(f"after penalty gCost: {gCost}")
                if node.ParentOutXYZ:
                    internal_gCost = node.ParentOutXYZ.DistanceTo(currentNode.CenterXYZ)
                    gCost += DB.UnitUtils.ConvertFromInternalUnits(internal_gCost, DB.UnitTypeId.Meters)
                    # print(f"added distance from currentNode center: {gCost}")
                if node.InXYZ: # Add distance to line center if node is a curve
                    internal_gCost = node.CenterXYZ.DistanceTo(inXYZ)
                    gCost += DB.UnitUtils.ConvertFromInternalUnits(internal_gCost, DB.UnitTypeId.Meters)
                    # print(f"added distance to next node center: {gCost}")

                # print(f"hcost: {hCost} Distance to Goal")
                # print(f"total gCost: {gCost} Distance to Parent")

                node.GCost = gCost + currentNode.GCost # Distance from Start
                # print(f"parent GCost: {currentNode.GCost}")
                # print(f"Node GCost: {node.GCost} Distance from Start")
                node.FCost = node.GCost + hCost # GCost + HCost

                # print(f"fcost: {node.FCost} Distance to Goal + Distance from Start")

                for openNode in newOpenNodes:
                    if node.Id != openNode.Id:
                        continue
                    if node.FCost < openNode.FCost:
                        newOpenNodes.remove(openNode)
                        # print(f"Node already exists and new FCost ist better")
                    else:
                        stop = True
                if stop: continue

                # Condition: Node already open
                for openNode in open:
                    if node.Id != openNode.Id:
                        continue
                    #if node.GCost < currentNode.GCost:
                    if node.GCost < openNode.GCost:
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
                
                newOpenNodes.append(node)

            open.extend(newOpenNodes)
            
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
        # print("Reached pathfinder end")
        return result
        #return "Ziel nicht im System? Versuche: " + str(c)

        
    except:
        print(traceback.format_exc())



def GetNearbyElements(point, categories, radiusmm = 1000) -> Generic.List[DB.Element]:
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

def project_point_onto_plane(plane, point):
    normal = plane.Normal
    origin = plane.Origin
    vec = point - origin
    distance = vec.DotProduct(normal)
    return point - distance * normal