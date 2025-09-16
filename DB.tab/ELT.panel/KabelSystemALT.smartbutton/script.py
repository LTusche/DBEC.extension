# -*- coding=utf-8 -*-
from pyrevit import DB, UI, HOST_APP
from pyrevit import framework, script, forms
#import System
import math
import traceback
import json
import time
from functools import wraps
from collections import OrderedDict

class Timer:
    def __init__(self, alerts, Benchmark):
        self.time = time
        self.Benchmark = Benchmark
        self.alerts = alerts
    def __call__(self, name):
        if self.Benchmark:
            self.name = name
            if self.name not in self.alerts:
                self.alerts[self.name] = 0
        return self
    def __enter__(self):
        if self.Benchmark:
            self.start = self.time.time()
        return self
    def __exit__(self, *args, **kwargs):
        if self.Benchmark:
            self.end = self.time.time()
            self.alerts[self.name] += self.end-self.start

class Updater(DB.IUpdater):
    def __init__(self, addin_id):
        self.id = updaterId
        self.DB = DB
        self.UI = UI
        self.HOST_APP = HOST_APP
        self.framework = framework
        self.math = math
        self.forms = forms
        self.json = json
        self.time = time
        self.wraps = wraps

        # Category filters
        typed_list = self.framework.System.Collections.Generic.List[self.DB.BuiltInCategory]([
            self.DB.BuiltInCategory.OST_CableTray,
            self.DB.BuiltInCategory.OST_CableTrayFitting])
        self.trayFilter = self.DB.ElementMulticategoryFilter(typed_list)

        typed_list = self.framework.System.Collections.Generic.List[DB.BuiltInCategory]([
            DB.BuiltInCategory.OST_CommunicationDevices,
            DB.BuiltInCategory.OST_DataDevices,
            DB.BuiltInCategory.OST_ElectricalFixtures,
            DB.BuiltInCategory.OST_FireAlarmDevices,
            DB.BuiltInCategory.OST_LightingDevices,
            DB.BuiltInCategory.OST_LightingFixtures,
            DB.BuiltInCategory.OST_NurseCallDevices,
            DB.BuiltInCategory.OST_SecurityDevices,
            DB.BuiltInCategory.OST_TelephoneDevices])
        self.devicesFilter = self.DB.ElementMulticategoryFilter(typed_list)

        self.distributorFilter = self.DB.ElementCategoryFilter(self.DB.BuiltInCategory.OST_ElectricalEquipment)

        self.preventUpdaterRerun = False
        self.updateRequiredQueue = framework.System.Collections.Generic.List[self.DB.ElementId]() # Elements that need to be rerun on next idle event
        self.traysToUpdateOnNextIdle = {}
        self.traysInRoomsCache = {} # Cache for trays in rooms. Key=RoomIntegerId, Value=List of Trays
        self.architectureRoomPhase = None
        self.architectureRoomSolids = {}
        self.architectureRoomType = "Raum" # Default Value. Difference of Room or MEP-Room because they use different functions
        self.kabelDatenParameter = None

        self.alerts = OrderedDict()
        self.Benchmark = False
        self.Timer = Timer(self.alerts, self.Benchmark)


        # For Traceback
        import sys
        self.sys = sys
        import linecache
        self.linecache = linecache

        self.traceback = traceback
        

    def GetUpdaterId(self):
        return self.id

    def GetUpdaterName(self):
        return "Kabelsystem Updater"

    def GetAdditionalInformation(self):
        return u"Führt das Kabelsystem im hintergrund mit."

    def GetChangePriority(self):
        return DB.ChangePriority.MEPFixtures

    def timing(func):
        @wraps(func)
        def wrap(self, *args, **kwargs):
            try:
                if self.Benchmark:
                    if func.__name__ not in self.alerts:
                        self.alerts[func.__name__] = 0
                    start = self.time.time()
                    result = func(self, *args, **kwargs)
                    end = self.time.time()
                    self.alerts[func.__name__] += end-start
                    return result
                else:
                    result = func(self, *args, **kwargs)
                    return result
            except:
                self.PrintException()
        return wrap

    
    def Execute(self, data):
        try:
            # Canceling excecution if the updater was triggered by itself or another updater.
            # This variable needs to be set to True whenever a change is made to the document
            # If a parameter is set to the same value it had before, its NOT counted as change.
            if self.preventUpdaterRerun:
                self.preventUpdaterRerun = False
                return

            self.alerts.clear()

            self.doc = data.GetDocument()
            self.app = self.doc.Application
            self.uidoc = self.HOST_APP.uidoc

            # Basic validity checks for the active document.
            if self.doc.IsFamilyDocument:
                return
            if not self.doc.IsModifiable:
                return
            if self.doc.IsLinked:
                return

            # Konfiguration laden
            globalParamId = self.DB.GlobalParametersManager.FindByName(self.doc,"TGA_VT-System-Konfiguration")
            if globalParamId.IntegerValue == -1:
                return

            globalParam = self.doc.GetElement(globalParamId)
            globalParamValue = globalParam.GetValue().Value
            try:
                self.config = self.json.loads(globalParamValue)
            except:
                return
                
            if "Systems" not in self.config:
                return

            if self.config["Systems"] == {}:
                return

            self.OffeneVerkabelungen = {} # Zum sammeln von Reihenverkabelung

            added_element_ids = data.GetAddedElementIds()
            modified_element_ids = data.GetModifiedElementIds()
            deleted_element_ids = data.GetDeletedElementIds()

            # Raumphase aus Konfiguration auslesen
            if "Räume" in self.config:
                roomPhaseId = int(self.config["Räume"]["PhaseId"])
                if "LinkId" in self.config["Räume"]:
                    linkId = int(self.config["Räume"]["LinkId"])
                    linkInstance = self.doc.GetElement(self.DB.ElementId(linkId))
                    # Sicherstellen, dass die linkId auf eine Verknüpfung zeigt
                    if not isinstance(linkInstance, self.DB.RevitLinkInstance):
                        linkName = linkInstance.get_Parameter(self.DB.BuiltInParameter.RVT_LINK_INSTANCE_NAME).AsString()
                        message = "Die Raum-Phase muss in der Kabelsystem Konfiguration neu zugewiesen werden."
                        if message not in self.alerts:
                            self.alerts[message] = []
                        return
                    document = linkInstance.GetLinkDocument()
                    if document == None:
                        linkName = linkInstance.get_Parameter(self.DB.BuiltInParameter.RVT_LINK_INSTANCE_NAME).AsString()
                        errorMessage = "Die folgenden Verknüpfungen müssen für das Kabelsystem geladen werden:"
                        # if message not in self.alerts:
                        #     self.alerts[message] = []
                        # if linkName not in self.alerts[message]:
                        #     self.alerts[message].append(linkName)
                        if linkName not in errorMessage:
                            errorMessage += "\n"+linkName
                        self.forms.alert(errorMessage)
                        return
                    self.architectureRoomPhase = document.GetElement(self.DB.ElementId(roomPhaseId))
                    self.roomDoc = document
                else:
                    self.architectureRoomPhase = self.doc.GetElement(self.DB.ElementId(roomPhaseId))
                    self.roomDoc = self.doc
                    
                if "Type" in self.config["Räume"]:
                    self.architectureRoomType = self.config["Räume"]["Type"]
            else:
                self.architectureRoomPhase = None


            """Kabeldatenparameter suchen"""
            #if self.kabelDatenParameter == None:
            collector = self.DB.FilteredElementCollector(self.doc)
            collector.WherePasses(self.devicesFilter)
            collector.WhereElementIsNotElementType()
            parameters = collector.FirstElement().GetParameters("TGA_Kabeldaten")
            if parameters.Count < 1:
                errorMessage = '"TGA_Kabeldaten" Parameter ist nicht angelegt\n ElementId: '
                errorMessage += str(collector.FirstElementId().IntegerValue)
                self.forms.alert(errorMessage)
                return
            self.kabelDatenParameter = parameters.Item[0]

            #print(str(self.time.time() - start))
            #start = self.time.time()


            if deleted_element_ids.Count > 0:
                elementsToModify = self.framework.System.Collections.Generic.List[self.DB.ElementId]()
                catFilterWithWires = self.DB.LogicalOrFilter(self.framework.System.Collections.Generic.List[self.DB.ElementFilter]([
                    self.trayFilter,
                    self.devicesFilter,
                    self.DB.ElementCategoryFilter(self.DB.BuiltInCategory.OST_Wire)
                ]))
                #catFilterWithWires = self.DB.LogicalOrFilter(self.trayFilter, self.DB.ElementCategoryFilter(self.DB.BuiltInCategory.OST_Wire))
                for deletedElementId in deleted_element_ids: 
                    collector = self.DB.FilteredElementCollector(self.doc)
                    collector.WherePasses(catFilterWithWires)
                    if elementsToModify.Count > 0:
                        collector.Excluding(elementsToModify)
                    collector.WhereElementIsNotElementType()
                    collector.WherePasses(
                        self.DB.ElementParameterFilter(
                            self.DB.FilterStringRule(
                                self.DB.ParameterValueProvider(
                                    self.kabelDatenParameter.Id
                                ),
                                self.DB.FilterStringContains(),
                                str(deletedElementId.IntegerValue)
                            )
                        )
                    )
                    elementsToModify.AddRange(collector.ToElementIds())
                
                #self.forms.alert(str(modified_element_ids.Count))
                # Zum entfernen gelöschter Elemente
                for elementId in elementsToModify:
                    element = self.doc.GetElement(elementId)
                    if self.trayFilter.PassesFilter(element):
                        parameters = element.GetParameters("TGA_Kabeldaten")
                        parameter = parameters.Item[0]
                        kabeldatenString = parameter.AsString()
                        try:
                            kabeldaten = self.json.loads(kabeldatenString)
                        except:
                            continue
                        self.traysToUpdateOnNextIdle[elementId.IntegerValue] = {
                            "Kabeldaten" : kabeldaten
                        }
                        for deletedElementId in deleted_element_ids:
                            for key in self.traysToUpdateOnNextIdle[elementId.IntegerValue]["Kabeldaten"]["Versorger-Verbraucher"].copy():
                                if str(deletedElementId.IntegerValue) in key:
                                    self.traysToUpdateOnNextIdle[elementId.IntegerValue]["Kabeldaten"]["Versorger-Verbraucher"].pop(key)
                        continue
                    if isinstance(element, self.DB.Electrical.Wire):
                        self.doc.Delete(elementId)
                        continue
                    if not self.devicesFilter.PassesFilter(element):
                        continue
                    self.func(element)


            for elementId in modified_element_ids:
                element = self.doc.GetElement(elementId)
                if element == None:
                    continue
                if isinstance(element, self.DB.ElementType):
                    # run func for all elements of type?
                    continue
                if isinstance(element, self.DB.Architecture.Room):
                    # run func for all elements inside rooms?
                    continue
                # FILTER FÜR ELEKTRISCHE AUSSTATTUNG
                if self.distributorFilter.PassesFilter(element):
                    #self.trayfunc(element)
                    continue
                if self.trayFilter.PassesFilter(element):
                    self.trayfunc(elementId)
                    continue
                if not self.devicesFilter.PassesFilter(element):
                    continue
                self.func(element)

            for elementId in added_element_ids:
                element = self.doc.GetElement(elementId)
                if self.trayFilter.PassesFilter(element):
                    self.trayfunc(elementId)
                    continue
                if not self.devicesFilter.PassesFilter(element):
                    continue
                if not isinstance(element, self.DB.FamilyInstance):
                    continue
                self.func(element)
            

            #for elementId in self.updateRequiredQueue[::-1]:
            #print(self.updateRequiredQueue.Count)
            # Elemente Spätes Update
            for index in range(self.updateRequiredQueue.Count-1, -1, -1):
                element = self.doc.GetElement(self.updateRequiredQueue.Item[index])
                #print(element)
                if element == None:
                    continue

                self.func(element)
                self.updateRequiredQueue.RemoveAt(index)

            # Kabeltrassen Spätes Update
            for trayIntId in self.traysToUpdateOnNextIdle.copy():
                self.writeTrayParameters(trayIntId)
                self.traysToUpdateOnNextIdle.pop(trayIntId)


            for vtKey in self.OffeneVerkabelungen:
                if self.OffeneVerkabelungen[vtKey] == "Reihenverkabelung":
                    self.reihenVerkabelung(vtKey)


            alertString = ""
            for alertTitle in self.alerts:
                if alertString != "":
                    alertString += "\n\n"
                alertString += alertTitle
                if isinstance(self.alerts[alertTitle], list):
                    for item in self.alerts[alertTitle]:
                        alertString += "\n"+str(item)
                    continue
                alertString += "\n"+ str(self.alerts[alertTitle])
            if alertString != "":
                self.forms.alert(alertString)
        except Exception as e:
            self.forms.alert(str(e))
            #self.PrintException()


    
    @timing
    def trayfunc(self, trayId):
        try:
            tray = self.doc.GetElement(trayId)
            if not isinstance(tray, self.DB.Electrical.CableTray):
                return

            # Remove the modified tray from cache
            for roomIntId in self.traysInRoomsCache.copy():
                for sTray in self.traysInRoomsCache[roomIntId]:
                    try:
                        if trayId.IntegerValue == sTray.Id.IntegerValue:
                            #self.alerts["resetRoomTray"] = ""
                            self.traysInRoomsCache.pop(roomIntId)
                            break
                    except:
                        self.traysInRoomsCache.pop(roomIntId)
                        break
            
            # Find related devices to run them after all the trays
            catOrFilter = self.DB.LogicalOrFilter(self.devicesFilter, self.distributorFilter)

            collector = self.DB.FilteredElementCollector(self.doc)
            collector.WherePasses(catOrFilter)
            if self.updateRequiredQueue.Count > 0:
                collector.Excluding(self.updateRequiredQueue)
            collector.WhereElementIsNotElementType()
            collector.WherePasses(
                self.DB.ElementParameterFilter(
                    self.DB.FilterStringRule(
                        self.DB.ParameterValueProvider(
                            self.kabelDatenParameter.Id
                        ),
                        self.DB.FilterStringContains(),
                        str(trayId.IntegerValue)
                    )
                )
            )
            for element in collector:
                self.updateRequiredQueue.Add(element.Id)
                
            if tray == None:
                return

            for parameter in tray.GetParameters("TGA_Kabeldaten"):
                try:
                    jsonData = self.json.loads(parameter.AsString())
                except:
                    continue

                for comb in jsonData["Versorger-Verbraucher"]:
                    l = comb.split("-")
                    elementId = self.DB.ElementId(int(l[2]))
                    if not self.updateRequiredQueue.Contains(elementId):
                        self.updateRequiredQueue.Add(elementId)

            points = []
            try:
                points.append(tray.Location.Curve.GetEndPoint(0))
                points.append(tray.Location.Curve.GetEndPoint(1))
            except:
                points.append(tray.Location.Point)
            # self.alerts["Find Rooms"] = ""
            # if "Room" not in self.alerts:
            #     self.alerts["Room"] = []
            for point in points:
                if point == None:
                    continue
                # self.alerts["Room"].append(point)
                room = None
                if self.architectureRoomType == "Raum":
                    room = self.roomDoc.GetRoomAtPoint(point, self.architectureRoomPhase)
                elif self.architectureRoomType == "MEP-Raum":
                    room = self.roomDoc.GetSpaceAtPoint(point, self.architectureRoomPhase)
                if room == None:
                    continue
                # self.alerts["Room"].append(room.Id.IntegerValue)
                # self.alerts["Rooms"] = str(self.traysInRoomsCache)
                if room.Id.IntegerValue in self.traysInRoomsCache:
                    self.traysInRoomsCache.pop(room.Id.IntegerValue)
                    # self.alerts["Reset Room"] = room.Id.IntegerValue

            

        except:
            self.PrintException()

    #@timing
    def GetElementLocation(self, element):
        point = None
        try:
            point = element.Location.Curve.Evaluate(0.5, False)
        except:
            point = element.Location.Point
        """
        if isinstance(element.Location, self.DB.LocationPoint):
            point = element.Location.Point
        else:
            point = element.Location.Curve.Evaluate(0.5, False)
        """
        if not point:
            return
        return point

    #@timing
    def MakePathOrthogonal(self, path):
        try:
            pathLength = len(path)
            enumerator = 0
            while enumerator < pathLength-1:
                firstPoint = path[enumerator]
                secondPoint = path[enumerator+1]
                xDifference = abs(firstPoint.X - secondPoint.X)
                yDifference = abs(firstPoint.Y - secondPoint.Y)
                if xDifference > 0.2 and yDifference > 0.2:
                    if xDifference > yDifference:
                        xyz = self.DB.XYZ(secondPoint.X, firstPoint.Y, secondPoint.Z)
                    else:
                        xyz = self.DB.XYZ(firstPoint.X, secondPoint.Y, secondPoint.Z)
                    path.insert(enumerator+1, xyz)
                    enumerator += 1
                    pathLength += 1
                enumerator += 1

            return path
        except:
            self.PrintException()

    #@timing
    def GetElementSystems(self, element):
        try:
            # Systemparameter sammeln
            systemTypeParameters = []
            systemExParameters = []
            parameters = element.Symbol.GetParameters("TGA_VT-Systeme")
            # if parameters.Count == 0:
            #     pass
            for parameter in parameters:
                systemTypeParameters.append(parameter)
            parameters = element.GetParameters("TGA_VT-Systeme-Ergänzung")
            for parameter in parameters:
                systemExParameters.append(parameter)
            if len(systemTypeParameters + systemExParameters) < 1:
                return []

            # Systemparameter auswerten
            elementSystems = []
            for parameter in systemTypeParameters + systemExParameters:
                systemStrings = parameter.AsString()
                if systemStrings == None:
                    continue
                for systemString in systemStrings.split(";"):
                    systemName = systemString.strip()
                    if systemName == "":
                        continue
                    if systemName not in elementSystems:
                        elementSystems.append(systemName)
            return elementSystems
        except:
            self.PrintException()

    #@timing
    def DeletePreviousCables(self, element):
        try:
            """Vorherige Kabel Löschen"""
            collector = self.DB.FilteredElementCollector(self.doc)
            collector.OfClass(self.DB.Electrical.Wire)
            #collector.OfCategory(self.DB.BuiltInCategory.OST_Wire)
            collector.WhereElementIsNotElementType()
            collector.WherePasses(
                self.DB.ElementParameterFilter(
                    self.DB.FilterStringRule(
                        self.DB.ParameterValueProvider(
                            self.kabelDatenParameter.Id
                        ),
                        self.DB.FilterStringContains(),
                        str(element.Id.IntegerValue)
                    )
                )
            )
            for wireId in collector.ToElementIds():
                if self.doc.GetElement(wireId) != None:
                    self.doc.Delete(wireId)
        except:
            self.PrintException()

    @timing
    def GetElementVerteiler(self, element, system, point):
        try:
            """Verteilerbereich aus Konfiguration auslesen"""
            if system not in self.config["Systems"]:
                message = "Die folgenden Kabelsysteme wurden noch keiner Phase zugewiesen:"
                if message not in self.alerts:
                    self.alerts[message] = []
                if system not in self.alerts[message]:
                    self.alerts[message].append(system)
                return
            if "PhaseId" not in self.config["Systems"][system]:
                message = "Es wurde noch keine Phase für die folgenden Systeme zugewiesen"
                if message not in self.alerts:
                    self.alerts[message] = []
                if system not in self.alerts[message]:
                    self.alerts[message].append(system)
                return
            systemPhaseId = int(self.config["Systems"][system]["PhaseId"])
            if "LinkId" in self.config["Systems"][system]:
                linkId = int(self.config["Systems"][system]["LinkId"])
                linkInstance = self.doc.GetElement(self.DB.ElementId(linkId))
                if not isinstance(linkInstance, self.DB.RevitLinkInstance):
                    return
                document = linkInstance.GetLinkDocument()
                if document == None:
                    linkName = linkInstance.get_Parameter(self.DB.BuiltInParameter.RVT_LINK_INSTANCE_NAME).AsString()
                    message = "Die folgenden Verknüpfungen müssen für das Kabelsystem geladen werden:"
                    if message not in self.alerts:
                        self.alerts[message] = []
                    if linkName not in self.alerts[message]:
                        self.alerts[message].append(linkName)
                    return
            else:
                document = self.doc

            systemPhase = document.GetElement(self.DB.ElementId(systemPhaseId))
            vtBereich = None
            
            architectureRoomType = "Raum"
            if "Type" in self.config["Systems"][system]:
                architectureRoomType = self.config["Systems"][system]["Type"]
            if architectureRoomType == "Raum":
                vtBereich = document.GetRoomAtPoint(point, systemPhase)
            elif architectureRoomType == "MEP-Raum":
                vtBereich = document.GetSpaceAtPoint(point, systemPhase)

            if vtBereich == None:
                elementId = str(element.Id.IntegerValue)
                message = 'Die folgenden Elemente befindet sich nicht in einem Verteilerbereich vom "'+ system + '" System:'
                if message not in self.alerts:
                    self.alerts[message] = []
                if elementId not in self.alerts[message]:
                    self.alerts[message].append(elementId)
                return
                #raise Exception("Das Element befindet sich nicht in einem Verteilerbereich")
            vtName = vtBereich.get_Parameter(self.DB.BuiltInParameter.ROOM_NAME).AsString()
            
            collector = self.DB.FilteredElementCollector(self.doc)
            collector.OfCategory(self.DB.BuiltInCategory.OST_ElectricalEquipment)
            collector.WhereElementIsNotElementType()
            collector.WherePasses(
                self.DB.ElementParameterFilter(
                    self.DB.FilterStringRule(
                        self.DB.ParameterValueProvider(
                            self.DB.ElementId(self.DB.BuiltInParameter.RBS_ELEC_PANEL_NAME)
                        ),
                        self.DB.FilterStringEquals(),
                        vtName
                    )
                )
            )

            vtCount = collector.GetElementCount()
            if vtCount < 1:
                message = 'Der Verteiler: "'+str(vtName)+'" konnte nicht gefunden werden'
                message = "Die folgenden Verteiler konnten nicht gefunden werden:"
                if message not in self.alerts:
                    self.alerts[message] = []
                if str(vtName) not in self.alerts[message]:
                    self.alerts[message].append(str(vtName))
            
            return collector.FirstElement()
        except:
            self.PrintException()

    @timing
    def func(self, element):
        try:

            self.DeletePreviousCables(element)
            
            point = self.GetElementLocation(element)

            elementSystems = self.GetElementSystems(element)

            for system in elementSystems:

                vtElement = self.GetElementVerteiler(element, system, point)
                if vtElement == None:
                    continue
                vtElementPoint = self.GetElementLocation(vtElement)

                vtKey = str(vtElement.Id.IntegerValue)+"-"+str(system)


                parameters = element.GetParameters("TGA_Kabeldaten")
                parameter = parameters.Item[0]
                value = parameter.AsString()
                try:
                    jsonData = self.json.loads(value)
                    if not isinstance(jsonData, dict):
                        errorMessage = "Fehlerhafte Kabeldaten in: "+str(element.Id.IntegerValue)
                        raise Exception(errorMessage)
                except:
                    jsonData = {"Systems":{}}

                # Remove unwanted distributors from element
                if vtKey not in jsonData["Systems"]:
                    jsonData["Systems"][vtKey] = {"Trays": []}
                for key in jsonData["Systems"].copy():
                    cKey = key.split("-")
                    if cKey[1] not in elementSystems:
                        jsonData["Systems"].pop(key)
                    if cKey[1] == system and cKey[0] != str(vtElement.Id.IntegerValue):
                        jsonData["Systems"].pop(key)

                if self.config["Systems"][system]["WiringType"] == "Sternverkabelung":
                    
                    room = None
                    vtElementRoom = None 

                    if self.architectureRoomPhase:
                        if self.architectureRoomType == "Raum":
                            room = self.roomDoc.GetRoomAtPoint(point, self.architectureRoomPhase)
                            vtElementRoom = self.roomDoc.GetRoomAtPoint(vtElementPoint, self.architectureRoomPhase)
                        elif self.architectureRoomType == "MEP-Raum":
                            room = self.roomDoc.GetSpaceAtPoint(point, self.architectureRoomPhase)
                            vtElementRoom = self.roomDoc.GetSpaceAtPoint(vtElementPoint, self.architectureRoomPhase)
                    if room and vtElementRoom and room.Id.IntegerValue == vtElementRoom.Id.IntegerValue:
                        startTrays = None
                        endTrays = None
                    else:
                        # Search for nearby cable trays
                        startTrays, startPoints = self.findCableTray(self.doc, point, room)
                        endTrays, endPoints = self.findCableTray(self.doc, vtElementPoint, vtElementRoom)

                    # Find path to the distributor
                    # If no trays could be found on either end, the freeStyleResult will be used
                    # The freeStyleResult is a direct path, ignoring the trays in between
                    if startTrays == None or endTrays == None:
                        result = self.freeStyleResult(point, vtElementPoint, False)
                        self.MakePathOrthogonal(result.Points)
                    else:
                        results = []
                        for startTray, startPoint in zip(startTrays, startPoints):
                            #? Check if previus result failed and skip if startelement is part of its network
                            for endTray, endPoint in zip(endTrays, endPoints):
                                results.append(self.pathfinder(startTray, endTray, startpoint=startPoint, endpoint=endPoint, traySystemRequirement=system))
                        # Find the best path from all of the results
                        result = results[0]
                        # Add the distance to the tray, to the result length
                        result.Length += result.Points[0].DistanceTo(point)*2 + result.Points[-1].DistanceTo(vtElementPoint)*2
                        if len(results) > 1:
                            #result.Length += result.Points[0].DistanceTo(point)*2 + result.Points[-1].DistanceTo(vtElementPoint)*2
                            for res in results[1:]:
                                if not res.Succeeded:
                                    continue
                                res.Length += res.Points[0].DistanceTo(point)*2 + res.Points[-1].DistanceTo(vtElementPoint)*2
                                if res.Length < result.Length or not result.Succeeded and res.Succeeded:
                                    result = res


                    # Create cable to distributor
                    # Currently Revit cables are used, which are only available in the current 2D View
                    ALLOWED_FLOORPLAN_VIEW_TYPES = [
                        self.DB.ViewType.FloorPlan,
                        self.DB.ViewType.CeilingPlan
                    ]
                    if "CreateWires" in self.config and self.doc.ActiveView.ViewType in ALLOWED_FLOORPLAN_VIEW_TYPES:
                        #if len(result.Points) > 1:

                        if isinstance(result, self.pathfinderResult):
                            """
                            pathToTray = self.MakePathOrthogonal([result.Points[0], point])
                            result.Points.pop(0)
                            for sPoint in pathToTray:
                                result.Points.insert(0, sPoint)

                            vtLocation = self.GetElementLocation(vtElement)
                            pathToTray = self.MakePathOrthogonal([result.Points[-1], vtLocation])
                            result.Points.pop(-1)
                            for sPoint in pathToTray:
                                result.Points.append(sPoint)
                            """
                            
                            result.Points.insert(0, point)
                            if result.Succeeded:
                                result.Points.append(vtElement.Location.Point)
                            

                        points = self.framework.System.Collections.Generic.List[self.DB.XYZ](result.Points)

                        for wireType in self.doc.Settings.ElectricalSetting.WireTypes:
                            wireTypeId = wireType.Id
                            break
                        wire = self.DB.Electrical.Wire.Create(
                            self.doc,
                            wireTypeId,
                            self.HOST_APP.active_view.Id,
                            self.DB.Electrical.WiringType.Chamfer,
                            points,
                            None,
                            None
                        )
                        for wireparameter in wire.GetParameters("TGA_Kabeldaten"):
                            wireparameter.Set(system+"-"+str(element.Id.IntegerValue)+" "+str(result.Succeeded))
                        #self.preventUpdaterRerun = True


                    """Skip if path is identical to old one"""
                    # if str(result.ElementIntegerIds) == str(jsonData["Systems"][vtKey]["Trays"]):
                    #     return

                    if result.Succeeded:
                        jsonData["Systems"][vtKey]["Trays"] = result.ElementIntegerIds
                        jsonData["Systems"][vtKey]["Successful"] = True
                    else:
                        jsonData["Systems"][vtKey]["Successful"] = False


                    newvalue = self.json.dumps(jsonData, ensure_ascii=False)
                    if newvalue != value:
                        parameter.Set(newvalue)
                        self.preventUpdaterRerun = True


                    """VERTEILER SCHREIBEN"""






                    """KABELTRASSEN SCHREIBEN"""

                    self.findTraysToUpdate(result=result, system=system, element=element, vtElement=vtElement)

                        
                elif self.config["Systems"][system]["WiringType"] == "Reihenverkabelung":
                    newvalue = self.json.dumps(jsonData, ensure_ascii=False)
                    if newvalue != value:
                        parameter.Set(newvalue)
                        self.preventUpdaterRerun = True

                    if vtKey not in self.OffeneVerkabelungen:
                        self.OffeneVerkabelungen[vtKey] = "Reihenverkabelung"

                    
                    
        except:
            self.PrintException()
    @timing
    def reihenVerkabelung(self, vtKey):
        try:
            typed_list = self.framework.System.Collections.Generic.List[self.DB.BuiltInCategory]([
                self.DB.BuiltInCategory.OST_CommunicationDevices,
                self.DB.BuiltInCategory.OST_DataDevices,
                self.DB.BuiltInCategory.OST_ElectricalEquipment,
                self.DB.BuiltInCategory.OST_ElectricalFixtures,
                self.DB.BuiltInCategory.OST_FireAlarmDevices,
                self.DB.BuiltInCategory.OST_LightingDevices,
                self.DB.BuiltInCategory.OST_LightingFixtures,
                self.DB.BuiltInCategory.OST_NurseCallDevices,
                self.DB.BuiltInCategory.OST_SecurityDevices,
                self.DB.BuiltInCategory.OST_TelephoneDevices])
                
            catFilter = self.DB.ElementMulticategoryFilter(typed_list)

            elementCollector = self.DB.FilteredElementCollector(self.doc)
            elementCollector.WherePasses(catFilter)
            elementCollector.WhereElementIsNotElementType()
            elementCollector.WherePasses(
                self.DB.ElementParameterFilter(
                    self.DB.FilterStringRule(
                        self.DB.ParameterValueProvider(
                            self.kabelDatenParameter.Id
                        ),
                        self.DB.FilterStringContains(),
                        vtKey
                    )
                )
            )

            self.DeletePreviousCables(elementCollector.FirstElement())

            vtIdString, system = vtKey.split("-")
            vtElement = self.doc.GetElement(self.DB.ElementId(int(vtIdString)))
            vtElementPoint = self.GetElementLocation(vtElement)

            points = []
            bestResults = []
            elements = elementCollector.ToElements()
            for element in elements:
                self.DeletePreviousCables(element)

                point = self.GetElementLocation(element)
                points.append(point)
                
                room = None
                vtElementRoom = None
                if self.architectureRoomPhase:
                    if self.architectureRoomType == "Raum":
                        room = self.roomDoc.GetRoomAtPoint(point, self.architectureRoomPhase)
                        vtElementRoom = self.roomDoc.GetRoomAtPoint(vtElementPoint, self.architectureRoomPhase)
                    elif self.architectureRoomType == "MEP-Raum":
                        room = self.roomDoc.GetSpaceAtPoint(point, self.architectureRoomPhase)
                        vtElementRoom = self.roomDoc.GetSpaceAtPoint(vtElementPoint, self.architectureRoomPhase)
                if room and vtElementRoom and room.Id.IntegerValue == vtElementRoom.Id.IntegerValue:
                    startElements = None
                    endElements = None
                else:
                    """Suche nach naheliegenden Kabeltrassen"""
                    startElements, startPoints = self.findCableTray(self.doc, point, room)
                    endElements, endPoints = self.findCableTray(self.doc, vtElementPoint, vtElementRoom)

                """Pfadsuche zum Verteiler"""
                if startElements == None or endElements == None:
                    result = self.freeStyleResult(point, vtElementPoint, False)
                    self.MakePathOrthogonal(result.Points)
                else:
                    results = []
                    for startElement, startPoint in zip(startElements, startPoints):
                        #? Check if previus result failed and skip if startelement is part of its network
                        for endElement, endPoint in zip(endElements, endPoints):
                            results.append(self.pathfinder(startElement, endElement, startpoint=startPoint, endpoint=endPoint, traySystemRequirement=system))

                    result = results[0]
                    result.Length += result.Points[0].DistanceTo(point)*2 + result.Points[-1].DistanceTo(vtElementPoint)*2
                    if len(results) > 1:
                        #result.Length += result.Points[0].DistanceTo(point)*2 + result.Points[-1].DistanceTo(vtElementPoint)*2
                        for res in results[1:]:
                            if not res.Succeeded:
                                continue
                            res.Length += res.Points[0].DistanceTo(point)*2 + res.Points[-1].DistanceTo(vtElementPoint)*2
                            if res.Length < result.Length or not result.Succeeded and res.Succeeded:
                                result = res

                bestResults.append(result)

            result = bestResults[0]
            firstElementIndex = 0


            # self.alerts["Length to beat"] = result.Length
            # self.alerts["New length"] = []
            for c, res in enumerate(bestResults):
                # self.alerts["New length"].append(elements.Item[c].Id.IntegerValue)
                # self.alerts["New length"].append(res.Length)
                if not result.Succeeded and res.Succeeded or res.Length < result.Length:
                    result = res
                    firstElementIndex = c

            firstElement = elements[firstElementIndex]

            #firstElement = elements[firstElementIndex]

            # if result.Succeeded:
            #     jsonData["Systems"][vtKey]["Trays"] = result.ElementIntegerIds
            #     jsonData["Systems"][vtKey]["Successful"] = True
            # else:
            #     jsonData["Systems"][vtKey]["Successful"] = False



            tour, tour_length = self.TSP(points, firstElementIndex, False)

            elements = [elements[index] for index in tour]
            tourPoints = [points[index] for index in tour]
            
            #self.MakePathOrthogonal(tourPoints)
            
            if isinstance(result, self.freeStyleResult):
                tourPoints.pop(0)

            for resultPoint in result.Points:
                tourPoints.insert(0, resultPoint)
            
            if result.Succeeded:
                tourPoints.insert(0, vtElementPoint)

            #self.alerts[str(tourPoints)] = ""
            #self.alerts[str(result.Points)] = ""
            
            ##### Kabel zum Ersten Element
            if "CreateWires" in self.config:
                if len(tourPoints) > 1:
                    points = self.framework.System.Collections.Generic.List[self.DB.XYZ](tourPoints)
                    """
                    tourPoints.Insert(0, point)
                    if result.Succeeded:
                        tourPoints.Add(vtElement.Location.Point)
                    """

                    for wireType in self.doc.Settings.ElectricalSetting.WireTypes:
                        wireTypeId = wireType.Id
                        break
                    wire = self.DB.Electrical.Wire.Create(
                        self.doc,
                        wireTypeId,
                        self.HOST_APP.active_view.Id,
                        self.DB.Electrical.WiringType.Chamfer,
                        tourPoints,
                        None,
                        None
                    )
                    elementIdsString = ""
                    for element in elements:
                        elementIdsString += str(element.Id.IntegerValue) + ","
                    for wireparameter in wire.GetParameters("TGA_Kabeldaten"):
                        wireparameter.Set(elementIdsString.strip(","))
                    if self.HOST_APP.version >= "2022":
                        parameter = wire.GetParameter(self.DB.ParameterTypeId.AllModelInstanceComments)
                    else:
                        parameter = wire.get_parameter(self.DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                    parameter.Set(str(tour_length/3.281 + result.Length/3.281))
                    #parameter.Set(str(tour_length))


            self.findTraysToUpdate(result=result, system=system, element=firstElement, vtElement=vtElement)


            #parameter.Set(self.json.dumps(jsonData, ensure_ascii=False))
            #self.preventUpdaterRerun = True

            """
            if result.Succeeded:
                jsonData["Systems"][vtKey]["Trays"] = result.ElementIntegerIds
                jsonData["Systems"][vtKey]["Successful"] = True
            else:
                jsonData["Systems"][vtKey]["Successful"] = False
            parameter.Set(self.json.dumps(jsonData, ensure_ascii=False))
            self.preventUpdaterRerun = True
            """

        except:
            self.PrintException()

    @timing
    def findCableTray(self, doc, point, room = None):
        try:
                
            #! FILTER FÜR KABELTRASSEN
            #! Frage: Was für System-Inkompatibilitäten gibt es ausser AV-SV und ELT-FMT?
            elementCount = 0
            if room:
                if room.Id.IntegerValue in self.traysInRoomsCache:
                    collector = self.traysInRoomsCache[room.Id.IntegerValue]
                    elementCount = collector.Count
                else:
                    #bbox = room.BoundingBox[self.uidoc.ActiveView]
                    #outline = self.DB.Outline(bbox.Min, bbox.Max)
                    if room.Id.IntegerValue not in self.architectureRoomSolids:
                        calculator = self.DB.SpatialElementGeometryCalculator(doc)
                        #roomsolid = calculator.CalculateSpatialElementGeometry(room).GetGeometry()
                        self.architectureRoomSolids[room.Id.IntegerValue] = calculator.CalculateSpatialElementGeometry(room)
                    
                    roomsolid = self.architectureRoomSolids[room.Id.IntegerValue].GetGeometry()
                    #self.alerts["RoomSolid"] = str(roomsolid)
                    collector = self.DB.FilteredElementCollector(doc)
                    collector.WherePasses(self.trayFilter)
                    collector.WhereElementIsNotElementType()
                    #collector.WherePasses(self.DB.BoundingBoxIntersectsFilter(outline))
                    collector.WherePasses(self.DB.ElementIntersectsSolidFilter(roomsolid))
                    self.traysInRoomsCache[room.Id.IntegerValue] = collector.ToElements()
                    elementCount = collector.GetElementCount()
            """
            if elementCount == 0:
                radius = 4000
                while elementCount == 0 and radius <= 4000:
                    sphere = self.CreateSphere(point, radius / 304.8)
                    radius += 2000

                    typed_list = self.framework.System.Collections.Generic.List[self.DB.BuiltInCategory]([
                        self.DB.BuiltInCategory.OST_CableTray,
                        self.DB.BuiltInCategory.OST_CableTrayFitting])
                    catFilter = self.DB.ElementMulticategoryFilter(typed_list)

                    collector = self.DB.FilteredElementCollector(doc)
                    collector.WherePasses(catFilter)
                    collector.WhereElementIsNotElementType()
                    collector.WherePasses(self.DB.ElementIntersectsSolidFilter(sphere))

                    elementCount = collector.GetElementCount()
            """
            if elementCount == 0:

                # excText = 'Es konnte keine Kabeltrasse für die folgenden Objekte gefunden werden:'
                # if excText not in self.alerts:
                #     self.alerts[excText] = []
                # self.alerts[excText].append(element.Name)

                return None, [point]
                #raise Exception(excText)
            
            trays = []
            distances = []
            closestPoints = []
            for tray in collector:
                try:
                    tray.Id
                except:
                    continue
                trays.append(tray)
                try:
                    distances.append(tray.Location.Curve.Distance(point))
                    closestPoints.append(tray.Location.Curve.Project(point).XYZPoint)
                except:
                    distances.append(tray.Location.Point.DistanceTo(point))
                    closestPoints.append(tray.Location.Point)
                # if isinstance(tray.Location, self.DB.LocationCurve):
                #     distances.append(tray.Location.Curve.Distance(point))
                #     closestPoints.append(tray.Location.Curve.Project(point).XYZPoint)
                # else:
                #     distances.append(tray.Location.Point.DistanceTo(point))
                #     closestPoints.append(tray.Location.Point)

            if trays == []:
                return None, [point]

            trays = [x for _, x in sorted(zip(distances, trays))]
            closestPoints = [x for _, x in sorted(zip(distances, closestPoints))]

            """
            closest = collector.FirstElement()
            closestDistance = closest.Location.Curve.Distance(point)
            closestPoint = closest.Location.Curve.Project(point).XYZPoint

            cableTrays = collector

            for tray in cableTrays:
                curve = tray.Location.Curve
                distance = curve.Distance(point)
                if distance < closestDistance:
                    closestDistance = distance
                    closest = tray 
                    closestPoint = closest.Location.Curve.Project(point).XYZPoint
            """
            return trays, closestPoints

        except:
            self.PrintException()
            return None, [point]

    def findTraysToUpdate(self, result, system, element, vtElement):
        try:

            # typed_list = self.framework.System.Collections.Generic.List[self.DB.BuiltInCategory]([
            #     self.DB.BuiltInCategory.OST_CableTray,
            #     self.DB.BuiltInCategory.OST_CableTrayFitting])
            # catFilter = self.DB.ElementMulticategoryFilter(typed_list)

            trayKey = str(vtElement.Id.IntegerValue)+"-"+str(system)+"-"+str(element.Id.IntegerValue)
            elementKey = str(system)+"-"+str(element.Id.IntegerValue)

            trayCollector = self.DB.FilteredElementCollector(self.doc)
            trayCollector.WherePasses(self.trayFilter)
            if result.ElementIds:
                exclusionList = self.framework.System.Collections.Generic.List[self.DB.ElementId](result.ElementIds)
                trayCollector.Excluding(exclusionList)
            trayCollector.WhereElementIsNotElementType()
            trayCollector.WherePasses(
                self.DB.ElementParameterFilter(
                    self.DB.FilterStringRule(
                        self.DB.ParameterValueProvider(
                            self.kabelDatenParameter.Id
                        ),
                        self.DB.FilterStringContains(),
                        elementKey
                    )
                )
            )

            for tray in result.Elements:
                if tray.Id.IntegerValue not in self.traysToUpdateOnNextIdle:
                    parameters = tray.GetParameters("TGA_Kabeldaten")
                    parameter = parameters.Item[0]
                    kabeldatenString = parameter.AsString()
                    try:
                        kabeldaten = self.json.loads(kabeldatenString)
                        if not isinstance(kabeldaten, dict):
                            raise Exception("Fehlerhafte JsonDaten")
                    except:
                        kabeldaten = {"Versorger-Verbraucher":{}}
                    self.traysToUpdateOnNextIdle[tray.Id.IntegerValue] = {
                        "Kabeldaten" : kabeldaten
                    }
                
                self.traysToUpdateOnNextIdle[tray.Id.IntegerValue]["Kabeldaten"]["Versorger-Verbraucher"][trayKey] = {
                    "Kabel" : []
                }
                
                # Einträge von Element aussortieren, bei denen der Verteiler nicht mehr stimmt.
                for k in self.traysToUpdateOnNextIdle[tray.Id.IntegerValue]["Kabeldaten"]["Versorger-Verbraucher"].copy():
                    if elementKey not in k:
                        continue
                    if str(vtElement.Id.IntegerValue) in k:
                        continue
                    self.traysToUpdateOnNextIdle[tray.Id.IntegerValue]["Kabeldaten"]["Versorger-Verbraucher"].pop(k)
                
                # newvalue = self.json.dumps(kabeldaten, ensure_ascii=False)
                # if newvalue != kabeldatenString:
                #     parameter.Set(newvalue)
                #     self.preventUpdaterRerun = True
                
                #self.traysToUpdateOnNextIdle[tray.Id.IntegerValue] = kabeldaten
                #self.writeTrayMtexts(tray, kabeldaten)

            for tray in trayCollector:
                if tray.Id.IntegerValue not in self.traysToUpdateOnNextIdle:
                    parameters = tray.GetParameters("TGA_Kabeldaten")
                    if parameters.Count < 1:
                        return
                    parameter = parameters.Item[0]
                    kabeldatenString = parameter.AsString()
                    try:
                        kabeldaten = self.json.loads(kabeldatenString)
                    except Exception as e:
                        print("Kabelsystem: "+e)
                        print(self.traceback.format_exc())
                        continue
                    self.traysToUpdateOnNextIdle[tray.Id.IntegerValue] = {
                        "Kabeldaten" : kabeldaten
                    }
                for k in self.traysToUpdateOnNextIdle[tray.Id.IntegerValue]["Kabeldaten"]["Versorger-Verbraucher"].copy():
                    if elementKey not in k:
                        continue
                    self.traysToUpdateOnNextIdle[tray.Id.IntegerValue]["Kabeldaten"]["Versorger-Verbraucher"].pop(k)
                # newvalue = self.json.dumps(kabeldaten, ensure_ascii=False)
                # if newvalue != kabeldatenString:
                #     parameter.Set(newvalue)
                #     self.preventUpdaterRerun = True

                # self.writeTrayMtexts(tray, kabeldaten)


        except:
            self.PrintException()

    @timing
    def writeTrayParameters(self, trayIntId):
        try:

            #tray = self.traysToUpdateOnNextIdle[trayIntId]["Tray"]
            kabeldaten = self.traysToUpdateOnNextIdle[trayIntId]["Kabeldaten"]
            tray = self.doc.GetElement(self.DB.ElementId(trayIntId))
            #self.alerts["TrayId"] = trayIntId
            if tray == None:
                return
            #parameter = self.traysToUpdateOnNextIdle[trayIntId]["Kabeldaten_Parameter"]

            kabeldatenString = self.json.dumps(kabeldaten, ensure_ascii=False)

            parameter = tray.GetParameters("TGA_Kabeldaten").Item[0]
            #if parameter.AsString() == kabeldatenString:
            #    return
            if parameter.AsString() != kabeldatenString:
                parameter.Set(kabeldatenString)
                self.preventUpdaterRerun = True

            von = ""
            nach = ""
            kabel = ""
            for key in sorted(kabeldaten["Versorger-Verbraucher"]):
                l = key.split("-")
                #von += "\n"+l[0]
                #nach += "\n"+l[2]
                versorger = self.doc.GetElement(self.DB.ElementId(int(l[0])))
                verbraucher = self.doc.GetElement(self.DB.ElementId(int(l[2])))
                
                if self.HOST_APP.version >= "2022":
                    parameter = versorger.GetParameter(self.DB.ParameterTypeId.RbsElecPanelName)
                else:
                    parameter = versorger.get_parameter(self.DB.BuiltInParameter.RBS_ELEC_PANEL_NAME)
                cables = kabeldaten["Versorger-Verbraucher"][key]["Kabel"]
                if cables == []:
                    von += "\n"+parameter.AsString()
                    nach += "\n"+verbraucher.Name
                for cable in cables:
                    kabel += "\n"+cable
                    von += "\n"+parameter.AsString()
                    nach += "\n"+verbraucher.Name
            try:
                mTextParameter = tray.GetParameters("TGA_VT-MText-Kabel").Item[0]
                mTextParameter.Set(kabel)
                #self.preventUpdaterRerun = True
            except:
                pass
            try:
                mTextParameter = tray.GetParameters("TGA_VT-MText-Von").Item[0]
                mTextParameter.Set(von)
                #self.preventUpdaterRerun = True
            except:
                pass
            try:
                mTextParameter = tray.GetParameters("TGA_VT-MText-Nach").Item[0]
                mTextParameter.Set(nach)
                #self.preventUpdaterRerun = True
            except:
                pass
        except:
            self.PrintException()

    def CreateSharedParameter(self, cat_list, instance=True, groupname="ELT", name="TGA_Kabeldaten", type=None):
        try:
            if type == None:
                if HOST_APP.version >= "2022":
                    type = DB.SpecTypeId.String.MultilineText
                else:
                    type = DB.ParameterType.MultilineText

            app = self.doc.Application
            
            
            sharedParameterFile = app.OpenSharedParameterFile()
            if sharedParameterFile == None:
                SharedParam = r"C:\SharedParameters.txt"
                app.SharedParametersFilename = SharedParam

            sharedGroups = sharedParameterFile.Groups
            try:
                exDef = sharedGroups.__getitem__(groupname).Definitions.__getitem__(name)
                #print("Shared Group and Shared Parameter created")
            except:
                try:
                    defOptions = self.db.ExternalDefinitionCreationOptions(name, type)
                    exDef = sharedGroups.__getitem__(groupname).Definitions.Create(defOptions)
                    #print("Shared Parameter created")
                except:
                    exDef = sharedGroups.Create(groupname).Definitions.Create(defOptions)
                    #print("Shared Parameter found")

            cat_set = app.Create.NewCategorySet()
            for c in cat_list:
                cat_set.Insert(self.doc.Settings.Categories.get_Item(c))

            binding = app.Create.NewTypeBinding(cat_set)
            if instance:
                binding = app.Create.NewInstanceBinding(cat_set)
            binding_map = self.doc.ParameterBindings

            #with self.transaction("Track Changes Parameter anlegen"):
            binding_map.Insert(exDef, binding, self.db.BuiltInParameterGroup.PG_IDENTITY_DATA)
                
            #print("parameter inserted into project")
            return True
        except:
            self.PrintException()

    @timing
    def trayAcceptsSystem(self, tray, traySystemRequirement):
        try:
            if not isinstance(tray, self.DB.Electrical.CableTray):
                return True
            traySystems = []

            instanceParameter = tray.GetParameters("TGA_VT-Systeme-Ergänzung")
            for parameter in instanceParameter:
                pvalue = parameter.AsString()
                if pvalue is None or pvalue == "":
                    continue
                for s in pvalue.split(";"):
                    traySystems.append(s.strip())

            typeParameter = self.doc.GetElement(tray.GetTypeId()).GetParameters("TGA_VT-Systeme")
            for parameter in typeParameter:
                pvalue = parameter.AsString()
                if pvalue is None or pvalue == "":
                    continue
                for s in pvalue.split(";"):
                    traySystems.append(s.strip())

            if len(traySystems) == 0:
                traySystems.append("AV")

            for traySystem in traySystems:
                if traySystem in traySystemRequirement:
                    return True
            # if traySystemRequirement not in traySystems:
            #     return False
            
            return False
            
        except:
            self.PrintException()

    @timing
    def pathfinder(self, startElement, endElement, startpoint=None, endpoint=None, traySystemRequirement="SV"):
        try:
            # A* Pathfinding algorithm
            startNode = self.Node(startElement)
            if startpoint:
                startNode.XYZ = startpoint

            endNode = self.Node(endElement)
            if startpoint:
                endNode.XYZ = endpoint
            
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
                
                open.pop(currentIndex)
                closed.append(currentNode)
                # Check if we found the end node
                if currentNode.Id == endNode.Id:
                    currentNode.XYZ = endNode.XYZ
                    result = self.pathfinderResult(startNode, currentNode, True)
                    current = currentNode
                    while current is not None:
                        result.Insert(0,current)
                        current = current.Parent
                    return result
                
                # Find Connected Nodes
                try:
                    connectors = currentNode.Element.MEPModel.ConnectorManager.Connectors
                except:
                    try:
                        connectors = currentNode.Element.ConnectorManager.Connectors
                    except:			
                        connectors = []
                
                connectedElements = []
                for connector in connectors:
                    for x in connector.AllRefs:
                        if x.Owner.Id != connector.Owner.Id:
                            node = self.Node(self.doc.GetElement(x.Owner.Id))
                            # if not node.XYZ.IsAlmostEqualTo(connector.Origin, 0.05):
                            #     currentNode.XYZ = connector.Origin
                            #     #node.XYZ = connector.Origin
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
                    
                    gCost = node.XYZ.DistanceTo(currentNode.XYZ)
                    hCost = node.XYZ.DistanceTo(endNode.XYZ)
                    node.HCost = hCost
                    node.GCost = gCost + currentNode.GCost
                    node.FCost = gCost + hCost
                    
                    # Condition: Node already open
                    for openNode in open[:]:
                        if node.Id == openNode.Id:
                            if node.GCost < currentNode.GCost:
                                #currentNode.Parent.Parent = currentNode
                                #currentNode.Parent = openNode
                                stop = True
                    if stop: continue

                    # Condition: Only allow trays of current system
                    if not self.trayAcceptsSystem(node.Element, traySystemRequirement):
                        continue

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
            return result
            #return "Ziel nicht im System? Versuche: " + str(c)

            
        except Exception as e:
            print("Kabelsystem: "+e)
            print(self.traceback.format_exc())

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
            self.Points.append(node.XYZ)
            self.ElementIds.append(node.Id)
            self.ElementIntegerIds.append(node.Id.IntegerValue)

        def Insert(self, index, node):
            self.Nodes.insert(index, node)
            self.Elements.insert(index, node.Element)
            self.Points.insert(index, node.XYZ)
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
            self.XYZ = None
            try:
                self.XYZ = element.Location.Curve.Evaluate(0.5,True)
            except:
                self.XYZ = element.Location.Point

    @timing
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

        loops = self.framework.System.Collections.Generic.List[self.DB.CurveLoop]()
        loops.Add(halfCircle)

        return self.DB.GeometryCreationUtilities.CreateRevolvedGeometry(frame, loops, 0, 2 * self.math.pi)
    
    @timing
    def TSP(self, points, starting_city_index = 0, returnToStart = False):
        """Traveling Salesman Problem"""
        try:

            city_coordinates = [(p.X, p.Y) for p in points]

            """Compute a distance_matrix for a set of points."""
            num_cities = len(city_coordinates)
            distance_matrix = {}      # dictionary to hold num_cities times num_cities distance_matrix
            for city_i in range(num_cities-1):
                for city_j in range(city_i+1,num_cities):
                    (x1,y1) = city_coordinates[city_i]
                    (x2,y2) = city_coordinates[city_j]
                    x_distance = x2 - x1
                    y_distance = y2 - y1
                    distance_matrix[city_i,city_j] = float(self.math.sqrt(x_distance*x_distance + y_distance*y_distance) + .5)
                    #distance_matrix[city_i,city_j] = dist((x1,y1), (x2,y2))
                    distance_matrix[city_j,city_i] = distance_matrix[city_i,city_j]

            """Return tour starting from city 'starting_city_index', using the Nearest Neighbor.

            Uses the Nearest Neighbor heuristic to construct a solution:
            - start visiting city starting_city_index
            - while there are remaining_cities cities, follow to the closest one
            - return to city starting_city_index
            """
            remaining_cities = range(num_cities)
            remaining_cities.remove(starting_city_index)
            current_city_index = starting_city_index
            tour = [starting_city_index]
            while remaining_cities != []:
                """Return the index of the node which is closest to 'current_city_index'."""
                closest_city_index = remaining_cities[0]
                min_distance = distance_matrix[current_city_index, closest_city_index]
                for city_i in remaining_cities[1:]:
                    if distance_matrix[current_city_index,city_i] < min_distance:
                        closest_city_index = city_i
                        min_distance = distance_matrix[current_city_index, closest_city_index]
                next_city_index = closest_city_index

                tour.append(next_city_index)
                remaining_cities.remove(next_city_index)
                current_city_index = next_city_index

            """Calculate the length of a tour according to distance distance_matrix."""
            if returnToStart:
                tour_length = distance_matrix[tour[-1], tour[0]]    # edge from current_city_index to first city of the tour
            else:
                tour_length = 0
            for city_i in range(1,len(tour)):
                if returnToStart:
                    tour_length += distance_matrix[tour[city_i], tour[city_i-1]]      # add length of edge from city city_i-1 to city_i
                    continue
                tour_length += distance_matrix[tour[city_i], tour[(city_i+1)%len(tour)]]


            """Obtain a local optimum starting from solution t; return solution length."""
            neighbor_list = None
            num_cities_in_tour = len(tour)
            if neighbor_list == None:
                """Compute a sorted list of the distances for each of the nodes.

                For each node, the entry is in the form [(d1,i1), (d2,i2), ...]
                where each tuple is a pair (distance,node).
                """
                neighbor_list = []
                for city_i in range(num_cities_in_tour):
                    distance_list = [(distance_matrix[city_i,city_j], city_j) for city_j in range(num_cities_in_tour) if city_j != city_i]
                    distance_list.sort()
                    neighbor_list.append(distance_list)
            
            """Improve tour by exchanging arcs"""
            while 1:
                newz = self.improve_tour(tour, tour_length, distance_matrix, neighbor_list, returnToStart)
                if newz < tour_length:
                    tour_length = newz
                else:
                    break

            # indeces = tour
            # tour Length = tour_length
            return tour, tour_length

        except:
            self.PrintException()
    
    #@timing
    def improve_tour(self, tour, tour_length, distance_matrix, neighbor_list, return_to_start):
        try:
            """Try to improve tour by exchanging arcs; return improved tour length.

            If possible, make a series of local improvements on the solution 'tour',
            using a breadth first strategy, until reaching a local optimum.
            """
            if return_to_start:
                tour_length += distance_matrix[tour[0], tour[-1]]

            num_cities = len(tour)
            tinv = [0 for city_i in tour]
            for city_i in range(num_cities):
                tinv[tour[city_i]] = city_i  # position of each city in 'tour'

            improved = True
            max_iter = 0
            while improved and max_iter < 10:
                max_iter += 1
                improved = False
                if return_to_start:
                    minus = 0
                else:
                    minus = -1

                for city_i in range(num_cities + minus):
                    city_a, city_b = tour[city_i], tour[(city_i + 1) % num_cities]
                    dist_ab = distance_matrix[city_a, city_b]

                    for dist_ac, city_c in neighbor_list[city_a]:
                        if dist_ac >= dist_ab:
                            break
                        city_j = tinv[city_c]
                        city_d = tour[(city_j + 1) % num_cities]
                        dist_cd = distance_matrix[city_c, city_d]
                        dist_bd = distance_matrix[city_b, city_d]
                        delta = (dist_ac + dist_bd) - (dist_ab + dist_cd)
                        if delta < 0:  # exchange decreases tour length
                            num_cities = len(tour)
                            if city_i > city_j:
                                city_i, city_j = city_j, city_i
                            assert city_i >= 0 and city_i < city_j - 1 and city_j < num_cities
                            path = tour[city_i + 1:city_j + 1]
                            path.reverse()
                            tour[city_i + 1:city_j + 1] = path
                            for k in range(city_i + 1, city_j + 1):
                                tinv[tour[k]] = k
                            tour_length += delta
                            improved = True
                            break
                    if improved:
                        continue
                    for dist_bd, city_d in neighbor_list[city_b]:
                        if dist_bd >= dist_ab:
                            break
                        city_j = tinv[city_d] - 1
                        if city_j == -1:
                            city_j = num_cities - 1
                        city_c = tour[city_j]
                        dist_cd = distance_matrix[city_c, city_d]
                        dist_ac = distance_matrix[city_a, city_c]
                        delta = (dist_ac + dist_bd) - (dist_ab + dist_cd)
                        if delta < 0:  # exchange decreases tour length
                            num_cities = len(tour)
                            if city_i > city_j:
                                city_i, city_j = city_j, city_i
                            assert city_i >= 0 and city_i < city_j - 1 and city_j < num_cities
                            path = tour[city_i + 1:city_j + 1]
                            path.reverse()
                            tour[city_i + 1:city_j + 1] = path
                            for k in range(city_i + 1, city_j + 1):
                                tinv[tour[k]] = k
                            tour_length += delta
                            improved = True
                            break

            tour_length = 0
            for city_i in range(num_cities-1):
                city_a,city_b = tour[city_i], tour[city_i+1]
                tour_length += distance_matrix[city_a,city_b]
            if return_to_start:
                tour_length += distance_matrix[tour[-1], tour[0]]
            # tour_length += distance_matrix[tour[-1], tour[0]]

            #self.alerts["TourLength"] = tour_length * 0.3048 

            return tour_length
        except:
            self.PrintException()

    def PrintException(self):
        if True:
            try:
                exc_type, exc_obj, tb = self.sys.exc_info()
                f = tb.tb_frame
                lineno = tb.tb_lineno
                filename = f.f_code.co_filename
                self.linecache.checkcache(filename)
                line = self.linecache.getline(filename, lineno, f.f_globals)
                string = 'EXCEPTION IN ({}, LINE {} "{}"): {}'.format(filename, lineno, line.strip(), exc_obj)
                self.alerts[string] = ""
                #self.forms.alert(string)
                #print(string)
            except Exception as e:
                self.forms.alert(e)


def registerUpdater(sender= None, args= None):
    try:
        updaterId = DB.UpdaterId(HOST_APP.addin_id, framework.System.Guid("c86f6253-c1fb-4a46-9d68-b7994e41d992"))

        typed_list = framework.System.Collections.Generic.List[DB.BuiltInCategory]([
            DB.BuiltInCategory.OST_CableTray,
            DB.BuiltInCategory.OST_CableTrayFitting,
            DB.BuiltInCategory.OST_CommunicationDevices,
            DB.BuiltInCategory.OST_DataDevices,
            DB.BuiltInCategory.OST_ElectricalEquipment,
            DB.BuiltInCategory.OST_ElectricalFixtures,
            DB.BuiltInCategory.OST_FireAlarmDevices,
            DB.BuiltInCategory.OST_LightingDevices,
            DB.BuiltInCategory.OST_LightingFixtures,
            DB.BuiltInCategory.OST_NurseCallDevices,
            DB.BuiltInCategory.OST_Rooms,
            DB.BuiltInCategory.OST_SecurityDevices,
            DB.BuiltInCategory.OST_TelephoneDevices])
            
        catFilter = DB.ElementMulticategoryFilter(typed_list)
        
        updater = Updater(HOST_APP.addin_id)
        DB.UpdaterRegistry.RegisterUpdater(updater)
        DB.UpdaterRegistry.SetIsUpdaterOptional(updaterId,True)
        DB.UpdaterRegistry.AddTrigger(updaterId, catFilter, DB.Element.GetChangeTypeElementDeletion())
        DB.UpdaterRegistry.AddTrigger(updaterId, catFilter, DB.Element.GetChangeTypeElementAddition())
        DB.UpdaterRegistry.AddTrigger(updaterId, catFilter, DB.Element.GetChangeTypeAny())

        script.toggle_icon(True, icon_size=script.ICON_LARGE)
        #catsWithTrays = DB.LogicalOrFilter(catFilter, DB.ElementCategoryFilter(DB.BuiltInCategory.OST_CableTrayFitting))
        #DB.UpdaterRegistry.AddTrigger(updaterId, catsWithTrays, DB.Element.GetChangeTypeElementDeletion())
    except Exception as e:
        print("Kabelsystem: "+e)
        print(traceback.format_exc())

def unregisterUpdater(sender = None, args = None):
    try:
        DB.UpdaterRegistry.RemoveAllTriggers(updaterId)
        DB.UpdaterRegistry.UnregisterUpdater(updaterId)

        script.toggle_icon(False, icon_size=script.ICON_LARGE)
        #print("Updater Unregistered")
    except Exception as e:
        print(e)


def checkForAutomaticActivation(sender = None, args = None):
    try:
        # from pyrevit import DB
        # import json
        ui_button_cmp = script.get_envvar("KABELSYSTEMBUTTON")
        script_cmp = script.get_envvar("KABELSYSTEMSCRIPT")
        event_doc = sender.ActiveUIDocument.Document
        if not isinstance(event_doc, DB.Document):
            if DB.UpdaterRegistry.IsUpdaterRegistered(updaterId):
                unregisterUpdater()
                ui_button_cmp.set_icon(script_cmp.directory+"\\off.png", 32)
            return
            #raise Exception("Zero Doc")
        globalParamId = DB.GlobalParametersManager.FindByName(event_doc,"TGA_VT-System-Konfiguration")
        if globalParamId.IntegerValue == -1:
            if DB.UpdaterRegistry.IsUpdaterRegistered(updaterId):
                unregisterUpdater()
                ui_button_cmp.set_icon(script_cmp.directory+"\\off.png", 32)
            return
            #raise Exception("Missing config")
        globalParam = event_doc.GetElement(globalParamId)
        globalParamValue = globalParam.GetValue().Value

        config = {}
        try:
            config = json.loads(globalParamValue)
        except:
            if DB.UpdaterRegistry.IsUpdaterRegistered(updaterId):
                unregisterUpdater()
                ui_button_cmp.set_icon(script_cmp.directory+"\\off.png", 32)

        if "UpdaterActive" not in config:
            return

        if config["UpdaterActive"] == True:
            if not DB.UpdaterRegistry.IsUpdaterRegistered(updaterId):
                registerUpdater()
                ui_button_cmp.set_icon(script_cmp.directory+"\\on.png", 32)
    except Exception as e:
        # if DB.UpdaterRegistry.IsUpdaterRegistered(updaterId):
        #     unregisterUpdater()
        try:
            forms.alert(str(traceback.format_exc()))
        except:
            print(str(e))
        #print(traceback.format_exc())
        return
    

# Stellt die Systeme im Konfigurationsfenster da
class KabelSystemItem(forms.Reactive):
    def __init__(self, name, systemType = None, phase = None):
        self.Name = name
        self._WiringType = KabelTypItem()
        self.Phase = PhasenItem()
        self.Type = "Raum"
    @forms.reactive
    def WiringType(self):
        return self._WiringType
    @WiringType.setter
    def WiringType(self, value):
        self._WiringType = value

        
# Stellt die Phasen im Konfigurationsfenster da
class PhasenItem(forms.Reactive):
    def __init__(self, phase=None, link=None):
        self.Name = ""
        self.LinkId = None
        self.Id = ""

        if phase == None: # To create empty phaseObjects
            return
        
        self.Name = phase.Name
        self.Id = phase.Id.IntegerValue
    
        if link != None:
            linkName = link.get_Parameter(DB.BuiltInParameter.RVT_LINK_INSTANCE_NAME).AsString()
            self.Name = str(linkName)+" > "+phase.Name
            self.LinkId = link.Id.IntegerValue

class KabelTypItem(forms.Reactive):
    def __init__(self, name=None):
        self._Name = name
    @forms.reactive
    def Name(self):
        return self._Name
    @Name.setter
    def Name(self, value):
        self._Name = value

# class ViewModel(forms.Reactive):
#     def __init__(self):
#         self.systems = framework.ObservableCollection[KabelSystemItem]()
#         self.phases = framework.ObservableCollection[PhasenItem]()
#         self.wireTypes = framework.ObservableCollection[KabelTypItem]()
#         pass

class Window(forms.WPFWindow, forms.Reactive):
    def __init__(self):
        try:
            self.systems = framework.ObservableCollection[KabelSystemItem]()
            self.phases = framework.ObservableCollection[PhasenItem]()
            self.wireTypes = framework.ObservableCollection[KabelTypItem]()
            self.roomTypes = framework.ObservableCollection[str](["Raum", "MEP-Raum"])
            pass

            self.traceback = traceback
        except:
            print(traceback.format_exc())

    def setup(self):
        try:
            #self.MainGrid.DataContext = Window
            if DB.UpdaterRegistry.IsUpdaterRegistered(updaterId):
                self.UpdaterStatusBox.Content = "Updater Aktiv"
                self.UpdaterStatusBox.IsChecked = True


            #self.SystemItemsControl.ItemsSource = self.systems
            self.ElementsListView.ItemsSource = self.systems

            self.roomPhaseBox.ItemsSource = self.phases
            self.roomPhaseBox.DisplayMemberPath = "Name"
            self.phaseColumn.ItemsSource = self.phases
            self.phaseColumn.DisplayMemberPath = "Name"
            self.typeColumn.ItemsSource = self.roomTypes
            self.roomTypeBox.ItemsSource = self.roomTypes
            self.roomTypeBox.SelectedIndex = 0
            #self.typeColumn.DisplayMemberPath = "Name"
            #self.wireTypeColumn.ItemsSource = self.wireTypes
            #self.wireTypeColumn.DisplayMemberPath = "Name"
            
            self.wireTypes.Add(KabelTypItem("Sternverkabelung"))
            self.wireTypes.Add(KabelTypItem("Reihenverkabelung"))

            self.phases.Add(PhasenItem()) # Empty item for deselection

            for phase in HOST_APP.doc.Phases:
                self.phases.Add(PhasenItem(phase))

            linkDoc = None
            links = DB.FilteredElementCollector(HOST_APP.doc).OfClass(DB.RevitLinkInstance)
            for link in links:
                linkDoc = link.GetLinkDocument()
                if linkDoc == None:
                    continue
                for phase in linkDoc.Phases:
                    self.phases.Add(PhasenItem(phase, link))

            self.checkSystemConfig()

        except:
            print(self.traceback.format_exc())

    def checkSystemConfig(self, sender=None, args=None):
        try:
            globalParamId = DB.GlobalParametersManager.FindByName(HOST_APP.doc,"TGA_VT-System-Konfiguration")
            self.globalParam = False
            if globalParamId.IntegerValue != -1:
                self.globalParam = HOST_APP.doc.GetElement(globalParamId)

            
            self.config = {"Systems": {}}
            try:
                globalParamValue = self.globalParam.GetValue().Value
                config = json.loads(globalParamValue)
                self.config = config # Seperated to catch the exception before writing self.config
            except:
                pass
                #print(traceback.format_exc())
                
            if "CreateWires" in self.config:
                self.createWires.IsChecked = True

            if "Räume" in self.config:
                for c, phase in enumerate(self.phases):
                    if c == 0: # First phase is empty
                        continue
                    if self.config["Räume"]["PhaseId"] == phase.Id:
                        self.roomPhaseBox.SelectedItem = phase
                        #systemObject.Phase = phase
                if "Type" in self.config["Räume"]:
                    self.roomTypeBox.SelectedItem = self.config["Räume"]["Type"]

            typed_list = framework.System.Collections.Generic.List[DB.BuiltInCategory]([
                DB.BuiltInCategory.OST_CommunicationDevices,
                DB.BuiltInCategory.OST_DataDevices,
                DB.BuiltInCategory.OST_ElectricalEquipment,
                DB.BuiltInCategory.OST_ElectricalFixtures,
                DB.BuiltInCategory.OST_FireAlarmDevices,
                DB.BuiltInCategory.OST_LightingDevices,
                DB.BuiltInCategory.OST_LightingFixtures,
                DB.BuiltInCategory.OST_NurseCallDevices,
                #DB.BuiltInCategory.OST_Rooms,
                DB.BuiltInCategory.OST_SecurityDevices,
                DB.BuiltInCategory.OST_TelephoneDevices])
                
            catFilter = DB.ElementMulticategoryFilter(typed_list)

            collector = DB.FilteredElementCollector(HOST_APP.doc)
            collector.WherePasses(catFilter)

            #self.LoadingPanel.Visibility = framework.System.Windows.Visibility.Visible
            #self.waitingAnimation.RepeatBehavior = framework.System.Windows.Media.Animation.RepeatBehavior(0)
            #framework.System.Windows.Media.Animation.RepeatBehavior.Count
            self.systems.Clear()
            self.subThread = self.dispatch(self.getSystems, collector)

        except Exception as e:
            print(self.traceback.format_exc())

    def getSystems(self, collector):
        try:
            #time.sleep(5)
            systems = []
            seperator = ";"
            if "SystemTrennzeichen" in self.config:
                sep = self.config["SystemTrennzeichen"]
                if sep != None and sep != "":
                    seperator = self.config["SystemTrennzeichen"]

            for element in collector:
                params = []
                if isinstance(element, DB.FamilySymbol):
                    params = element.GetParameters("TGA_VT-Systeme")
                else:
                    params = element.GetParameters("TGA_VT-Systeme-Ergänzung")
                for parameter in params:
                    systemStrings = parameter.AsString()
                    if systemStrings == None:
                        continue
                    for systemString in systemStrings.split(seperator):
                        systemName = systemString.strip()
                        if systemName == "":
                            continue
                        if systemName not in systems:
                            systems.append(systemName)
            self.dispatch(self.addSystems, systems)

        except Exception as e:
            self.dispatch(self.printres, e)

    def addSystems(self, systems):
        try:
            #print(systems)
            for systemName in sorted(systems):
                systemObject = KabelSystemItem(systemName)
                self.systems.Add(systemObject)
                #print(self.config)
                systemObject.WiringType = self.wireTypes.Item[0]
                if systemName not in self.config["Systems"]:
                    continue

                if "PhaseId" in self.config["Systems"][systemName]:
                    found = False
                    for c, phase in enumerate(self.phases):
                        if c == 0: # First phase is empty
                            continue
                        if "LinkId" in self.config["Systems"][systemName] and phase.LinkId == None:
                            # Solves: If a linked phase has the same id as any local phase, it would take the local phase.
                            continue
                        if self.config["Systems"][systemName]["PhaseId"] == phase.Id:
                            systemObject.Phase = phase
                            found = True
                            break
                    if not found:
                        phase = PhasenItem()
                        phase.Id = self.config["Systems"][systemName]["PhaseId"]
                        phase.Name = self.config["Systems"][systemName]["PhaseName"]
                        if "LinkId" in self.config["Systems"][systemName]:
                            phase.Name += " (Nicht Geladen)" # Is later removed via .replace()
                            phase.LinkId = self.config["Systems"][systemName]["LinkId"]
                        else:
                            phase.Name += " (Entfernt)" # Is later removed via .replace()
                        self.phases.Add(phase)
                        systemObject.Phase = phase


                if "WiringType" in self.config["Systems"][systemName]:
                    for wiringType in self.wireTypes:
                        if self.config["Systems"][systemName]["WiringType"] == wiringType.Name:
                            systemObject.WiringType = wiringType

                if "Type" in self.config["Systems"][systemName]:
                    systemObject.Type = self.config["Systems"][systemName]["Type"]
                    

            self.LoadingPanel.Visibility = framework.System.Windows.Visibility.Collapsed
            self.waitingAnimation.Storyboard.Stop(self.LoadingPanel)
        except Exception as e:
            print(self.traceback.format_exc())

    def printres(self, res):
        print(res)

    def toggleCheckbox(self, sender=None, args=None):
        try:
            if sender.IsChecked:
                if not DB.UpdaterRegistry.IsUpdaterRegistered(updaterId):
                    registerUpdater()
                self.UpdaterStatusBox.Content = "Updater Aktiv"
            if not sender.IsChecked:
                if DB.UpdaterRegistry.IsUpdaterRegistered(updaterId):
                    unregisterUpdater()
                self.UpdaterStatusBox.Content = "Updater Inaktiv"
            pass
        except Exception as e:
            print("Kabelsystem: "+e)

    def verkabelungsartButtonClick(self, sender, args):
        try:
            subWindow = WiringConfigWindow("WiringConfigWindow.xaml", sender)
            subWindow.Owner = self
            subWindow.show_dialog()
            #print("weeeewawd")
        except Exception as e:
            print(self.traceback.format_exc())

    def DataGrid_StartCellEdit(self, sender, args):
        try:
            if isinstance(args.OriginalSource, framework.System.Windows.Controls.DataGridCell):
                sender.BeginEdit(args)
        except Exception as e:
            print(self.traceback.format_exc())

    def waitForSubThread(self):
        try:
            self.subThread.join(10.0)
            if not self.subThread.is_alive():
                self.dispatch(self.confirmAndClose)
            else:
                raise Exception("SubThread konnte nicht geschlossen werden")
        except Exception as e:
            self.dispatch(self.printres, e)

    def confirmAndClose(self, sender = None, args = None):
        try:
            if self.subThread.is_alive() and sender:
                sender.Content = "Bitte warten.."
                self.dispatch(self.waitForSubThread)
                return
            
            config = {"Systems": {}}
            for system in self.systems:
                config["Systems"][system.Name] = {}
                if system.Phase.Name != "":
                    config["Systems"][system.Name]["PhaseId"] = system.Phase.Id
                    system.Phase.Name = system.Phase.Name.replace(" (Nicht Geladen)", "")
                    system.Phase.Name = system.Phase.Name.replace(" (Entfernt)", "")
                    config["Systems"][system.Name]["PhaseName"] = system.Phase.Name.replace(" (Nicht Geladen)", "")
                    if system.Phase.LinkId != None:
                        config["Systems"][system.Name]["LinkId"] = system.Phase.LinkId
                config["Systems"][system.Name]["Type"] = system.Type
                if system.WiringType != None:
                    config["Systems"][system.Name]["WiringType"] = system.WiringType.Name
                if config["Systems"][system.Name] == {}:
                    config["Systems"].pop(system.Name)
            
            if self.roomPhaseBox.SelectedIndex not in [-1, 0]:
                config["Räume"] = {}
                selectedPhase = self.roomPhaseBox.SelectedItem
                config["Räume"]["PhaseId"] = selectedPhase.Id
                if selectedPhase.LinkId != None:
                    config["Räume"]["LinkId"] = selectedPhase.LinkId
                config["Räume"]["Type"] = self.roomTypeBox.SelectedItem

            if self.createWires.IsChecked:
                config["CreateWires"] = True

            config["UpdaterActive"] = self.UpdaterStatusBox.IsChecked

            #config = {k: v for k, v in config.items() if v}
            jsonString = json.dumps(config, ensure_ascii=False)
            paraValue = DB.StringParameterValue(jsonString)
            transaction = DB.Transaction(HOST_APP.doc, "Kabelsystem Konfiguration Speichern")
            transaction.Start()
            try:
                if self.globalParam == False:
                    if HOST_APP.version >= "2022":
                        self.globalParam = DB.GlobalParameter.Create(HOST_APP.doc, "TGA_VT-System-Konfiguration", DB.SpecTypeId.String.MultilineText)
                    else:
                        self.globalParam = DB.GlobalParameter.Create(HOST_APP.doc, "TGA_VT-System-Konfiguration", DB.ParameterType.MultilineText)
                self.globalParam.SetValue(paraValue)
                transaction.Commit()
            except:
                transaction.RollBack()
                print(self.traceback.format_exc())
            self.Close()
        except Exception as e:
            print(self.traceback.format_exc())

    def onClosed(self, sender, args):
        try:
            """
            if self.UpdaterStatusBox.IsChecked:
                #print("register")
                #print(updaterId)
                if not DB.UpdaterRegistry.IsUpdaterRegistered(updaterId):
                    registerUpdater()
            elif not self.UpdaterStatusBox.IsChecked:
                #print("unregister")
                #print(updaterId)
                if DB.UpdaterRegistry.IsUpdaterRegistered(updaterId):
                    unregisterUpdater()
            """
            pass
        except:
            print(self.traceback.format_exc())

#import os.path as op

class WiringConfigWindow(forms.WPFWindow, forms.Reactive):
    def __init__(self, xaml_source, sender):
        try:
            super(WiringConfigWindow, self).__init__(xaml_source)

            self.sender = sender
            self.DataContext = sender.DataContext
            pass
        except:
            print(traceback.format_exc())
    def On_Loaded(self, sender, args):
        try:
            self.WiringTypeBox.ItemsSource = self.Owner.wireTypes

        except:
            print(traceback.format_exc())

updaterId = DB.UpdaterId(HOST_APP.addin_id, framework.System.Guid("c86f6253-c1fb-4a46-9d68-b7994e41d992"))

if __name__ == "__main__":
    updaterId = DB.UpdaterId(HOST_APP.addin_id, framework.System.Guid("c86f6253-c1fb-4a46-9d68-b7994e41d992"))

    window = script.load_ui(Window(), 'ui.xaml')
    # show modal or nonmodal
    window.show_dialog()


def __selfinit__(script_cmp, ui_button_cmp, __rvt__):
    try:
        script.set_envvar("KABELSYSTEMBUTTON", ui_button_cmp)
        script.set_envvar("KABELSYSTEMSCRIPT", script_cmp)

        updaterId = DB.UpdaterId(HOST_APP.addin_id, framework.System.Guid("c86f6253-c1fb-4a46-9d68-b7994e41d992"))

        handler = framework.EventHandler[UI.Events.ViewActivatedEventArgs](checkForAutomaticActivation)
        __rvt__.ViewActivated += handler
        if DB.UpdaterRegistry.IsUpdaterRegistered(updaterId):
            ui_button_cmp.set_icon(script_cmp.directory+"\\on.png", script.ICON_LARGE)
        #script.set_envvar("KABELSYSTEMHANDLER", handler)
        return True
    except Exception:
        return False