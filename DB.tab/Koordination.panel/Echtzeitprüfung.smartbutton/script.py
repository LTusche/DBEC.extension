# -*- coding=utf-8 -*-

from pyrevit import DB, UI, HOST_APP, ApplicationServices
from pyrevit import framework, script, forms
#from pyrevit.api import Autodesk
import math
import traceback
import json
import time
import datetime
from functools import wraps
from collections import OrderedDict
import sys
#from System import EventHandler

class Timer:
    def __init__(self, alerts, Benchmark):
        self.time = time
        self.Benchmark = Benchmark
        self.alerts = alerts
        self.timerDict = {}
    def __call__(self, name):
        if self.Benchmark:
            self.name = name
            if self.name not in self.alerts:
                self.alerts[self.name] = 0
            self.timerDict[self.name] = self.time.time()
        return self
    def __enter__(self):
        if self.Benchmark:
            pass
            #self.start = self.time.time()
        return self
    def __exit__(self, *args, **kwargs):
        if self.Benchmark:
            #self.end = self.time.time()
            self.alerts[self.name] += self.time.time() - self.timerDict[self.name]
            #self.alerts[self.name] += self.end-self.start

class Updater(DB.IUpdater):
    def __init__(self, addin_id, mainCatFilter):
        self.id = updaterId
        self.DB = DB
        self.UI = UI
        #self.Autodesk = Autodesk
        self.ApplicationServices = ApplicationServices
        self.HOST_APP = HOST_APP
        self.framework = framework
        self.math = math
        self.forms = forms
        self.json = json
        self.time = time
        self.datetime = datetime
        self.wraps = wraps
        self.script = script

        self.mainCatFilter = mainCatFilter
        typed_list = self.framework.System.Collections.Generic.List[DB.BuiltInCategory]([
            DB.BuiltInCategory.OST_PipeInsulations,
            DB.BuiltInCategory.OST_DuctInsulations
            ])
        self.insulationFilter = self.DB.ElementMulticategoryFilter(typed_list)

        self.alreadyExecuted = False
        self.customUpdaterData = []
        self.lightingFixtureSourceId = self.DB.ElementId(self.DB.BuiltInCategory.OST_LightingFixtureSource).IntegerValue
        
        self.alerts = OrderedDict()
        self.Benchmark = False
        self.Timer = Timer(self.alerts, self.Benchmark)

        if self.script.get_envvar("transientElementIds") == None:
            self.script.set_envvar("transientElementIds", {})

        # For Traceback
        import sys
        self.sys = sys
        import linecache
        self.linecache = linecache

        self.traceback = traceback
        

    def GetUpdaterId(self):
        return self.id

    def GetUpdaterName(self):
        return u"Echtzeit Kollisionsprüfung"

    def GetAdditionalInformation(self):
        return u"Führt beim ändern und erstellen von Objekten automatisch eine Kollisionsprüfung durch."

    def GetChangePriority(self):
        return DB.ChangePriority.DetailComponents

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
            # Canceling excecution if the updater was triggered by itself.
            if self.alreadyExecuted:
                self.alreadyExecuted = False
                #print("Already Executed")
                return

            self.alerts.clear()

            self.doc = data.GetDocument()
            self.app = self.doc.Application
            self.uidoc = self.HOST_APP.uidoc
            
            transaction = None
            # Basic validity checks for the active document.
            if self.doc.IsFamilyDocument:
                return
            if not self.doc.IsModifiable:
                if isinstance(data, self.CustomUpdaterData):
                    transaction = self.DB.Transaction(self.doc, "Echtzeitprüfung")
                    transaction.Start()
                    
                else:
                    return
            if self.doc.IsLinked:
                return
            
            # Konfiguration laden

            cfgLinks = self.script.get_config("KOO").get_option("links")

            projectId = str(self.doc.ProjectInformation.UniqueId)

            
            self.documentsToClashCheck = []
            self.documentsToClashCheck.append(self.doc)

            if projectId in cfgLinks:
                for instanceId in cfgLinks[projectId]:
                    linkInstance = self.doc.GetElement(self.DB.ElementId(int(instanceId)))
                    if not isinstance(linkInstance, self.DB.RevitLinkInstance):
                        continue
                    linkDoc = linkInstance.GetLinkDocument()
                    if not isinstance(linkDoc, self.DB.Document):
                        continue
                    self.documentsToClashCheck.append(linkDoc)



            # globalParamId = self.DB.GlobalParametersManager.FindByName(self.doc,"TGA_Clash-Konfiguration")
            # if globalParamId.IntegerValue == -1:
            #     return

            # globalParam = self.doc.GetElement(globalParamId)
            # globalParamValue = globalParam.GetValue().Value
            # self.config = {"Links": [], "Categories":[]}
            # try:
            #     self.config = self.json.loads(globalParamValue)
            # except:
            #     return
            # for instanceId in self.config["Links"]:
            #     if not self.config["Links"][instanceId]["Enabled"]:
            #         continue
            #     if int(instanceId) == -1:
            #         self.documentsToClashCheck.append(self.doc)
            #         continue
            #     linkInstance = self.doc.GetElement(self.DB.ElementId(int(instanceId)))
            #     if not isinstance(linkInstance, self.DB.RevitLinkInstance):
            #         continue
            #     linkDoc = linkInstance.GetLinkDocument()
            #     if not isinstance(linkDoc, self.DB.Document):
            #         continue
            #     self.documentsToClashCheck.append(linkDoc)


            self.transientElementIds = self.script.get_envvar("transientElementIds")
            
            # for category in self.doc.Settings.Categories:
            #     if category.Id.IntegerValue == self.DB.ElementId(self.DB.BuiltInCategory.OST_ElectricalEquipment).IntegerValue:
            #         self.style = category.GetGraphicsStyle(self.DB.GraphicsStyleType.Projection)
            #         break

            materialId = self.DB.ElementId.InvalidElementId

            materialCollector = self.DB.FilteredElementCollector(self.doc)
            materialCollector.OfClass(self.DB.Material)
            for material in materialCollector:
                if material.Name == "ClashMaterial":
                    materialId = material.Id
                    break

            if materialId == self.DB.ElementId.InvalidElementId:
                materialId = self.DB.Material.Create(self.doc, "ClashMaterial")
                newMat = self.doc.GetElement(materialId)
                newMat.Color = self.DB.Color(255,0,0)
                newMat.Transparency = 20


            self.solidOptions = self.DB.SolidOptions(materialId, self.DB.ElementId.InvalidElementId)
                
            added_element_ids = data.GetAddedElementIds()
            modified_element_ids = data.GetModifiedElementIds()
            deleted_element_ids = data.GetDeletedElementIds()

            elementcount = added_element_ids.Count
            elementcount += modified_element_ids.Count
            elementcount += deleted_element_ids.Count

            if elementcount > 500:
                res = self.forms.alert(
                    "Die Echtzeitprüfung ist davor "+str(elementcount)+" Elemente zu prüfen.\n\n"
                    "Fortfahren?",
                    None,
                    ok=False, yes=True, no=True
                    )
                if not res:
                    return

            for elementId in deleted_element_ids:
                elementIdValue = elementId.IntegerValue
                for clashKey in self.transientElementIds:
                    if str(elementIdValue) in str(clashKey):
                        for index, tId in reversed(list(enumerate(self.transientElementIds[clashKey]))):
                            try:
                                transientElement = self.doc.GetElement(tId)
                                if transientElement.IsTransient:
                                    self.doc.Delete(tId)
                                    del self.transientElementIds[clashKey][index]
                            except:
                                pass

            for elementId in modified_element_ids:
                element = self.doc.GetElement(elementId)
                if element == None:
                    continue
                if isinstance(element, self.DB.ElementType):
                    continue
                if not self.mainCatFilter.PassesFilter(element):
                    continue
                attr = getattr(element, "SuperComponent", None)
                if attr is not None:
                    if element.SuperComponent.Id in modified_element_ids:
                        continue
                #     for clashKey in self.transientElementIds:
                #         if str(element.Id.IntegerValue) in str(clashKey):
                #             for index, tId in reversed(list(enumerate(self.transientElementIds[clashKey]))):
                #                 try:
                #                     transientElement = self.doc.GetElement(tId)
                #                     if transientElement.IsTransient:
                #                         self.doc.Delete(tId)
                #                         del self.transientElementIds[clashKey][index]
                #                 except:
                #                     pass
                #     continue
                self.func(element)

            for elementId in added_element_ids:
                element = self.doc.GetElement(elementId)
                if element == None:
                    continue
                if isinstance(element, self.DB.ElementType):
                    continue
                if not self.mainCatFilter.PassesFilter(element):
                    continue
                # attr = getattr(element, "SuperComponent", None)
                # if attr is not None:
                #     continue
                self.func(element)

            # header_text = "Achtung!"
            # main_text = "Kollision verursacht"
            # timestamp = self.datetime.datetime.now()
            # self.forms.show_balloon(header_text, main_text, tooltip='toolwtip', group='group', is_favourite=False, is_new=False, timestamp = timestamp, click_result = forms.result_item_result_clicked)

            alertString = ""
            for alertTitle in self.alerts:
                if alertString != "":
                    alertString += "\n\n"
                alertString += str(alertTitle)
                if isinstance(self.alerts[alertTitle], list):
                    for item in self.alerts[alertTitle]:
                        alertString += "\n"+str(item)
                    continue
                alertString += "\n"+ str(self.alerts[alertTitle])
            if alertString != "":
                self.forms.alert(alertString)
                
            self.script.set_envvar("transientElementIds", self.transientElementIds)

            if transaction:
                transaction.Commit()
        except Exception as e:
            self.forms.alert(str(self.traceback.format_exc()))
            if transaction:
                transaction.RollBack()
            #self.PrintException()

    @timing
    def func(self, element):
        try:
            elementIdValue = element.Id.IntegerValue

            if not isinstance(element, self.DB.Element):
                return

            attr = getattr(element, "Symbol", None)
            if attr != None:
                ifcParameter = element.Symbol.get_Parameter(self.framework.System.Guid("f53d1285-ae3d-4992-a3f1-2e7978be529a"))
                if ifcParameter != None:
                    ifcParameterValue = ifcParameter.AsString()
                    if isinstance(ifcParameterValue,str):
                        if ifcParameterValue.upper() == "PROVISIONFORVOID":
                            return

            for clashKey in self.transientElementIds:
                if str(elementIdValue) in str(clashKey):
                    for index, tId in reversed(list(enumerate(self.transientElementIds[clashKey]))):
                        try:
                            transientElement = self.doc.GetElement(tId)
                            if transientElement.IsTransient:
                                self.doc.Delete(tId)
                                del self.transientElementIds[clashKey][index]
                        except:
                            pass

            pass
            options = self.DB.Options(
                IncludeNonVisibleObjects = False,
                DetailLevel = self.DB.ViewDetailLevel.Fine
                #View = self.uidoc.ActiveView
            )

            tolerance = (0,0,0,0)
            elementGeometry = self.GetBasicElementGeometry(element, options, tolerance)
            if elementGeometry.Count == 0:
                return
            #elementGeometry = self.GetElementGeometry(element, options)

            provisionForVoids = self.framework.System.Collections.Generic.List[self.DB.Element]()
            clashGeometries = self.framework.System.Collections.Generic.List[object]()
            clashKeys = self.framework.System.Collections.Generic.List[object]()
            for document in self.documentsToClashCheck:

                clashCollector = self.DB.FilteredElementCollector(document)
                """EXCLUSION LIST"""
                exclusionList = self.framework.System.Collections.Generic.List[self.DB.ElementId]()
                #exclusionList.Add(element.Id)
                attr = getattr(element, "HostElementId", None)
                if attr is not None:
                    exclusionList.Add(element.HostElementId)
                for dependentElementId in element.GetDependentElements(None):
                    exclusionList.Add(dependentElementId)
                
                try:
                    connectors = element.MEPModel.ConnectorManager.Connectors
                except:
                    try:
                        connectors = element.ConnectorManager.Connectors
                    except:			
                        connectors = []
                
                for connector in connectors:
                    for x in connector.AllRefs:
                        if x.Owner.Id == connector.Owner.Id:
                            continue
                        exclusionList.Add(x.Owner.Id)
                        for dependentElementId in x.Owner.GetDependentElements(self.insulationFilter):
                            exclusionList.Add(dependentElementId)

                clashCollector.Excluding(exclusionList)
                clashCollector.WherePasses(self.mainCatFilter)
                clashCollector.WhereElementIsNotElementType()
                
                # bboxFilters = self.framework.System.Collections.Generic.List[self.DB.ElementFilter]()
                # for geom in elementGeometry:
                #     bbox = geom.GetBoundingBox()
                #     # minPoint = self.DB.XYZ(bbox.Min.X, bbox.Min.Y, bbox.Min.Z)
                #     # maxPoint = self.DB.XYZ(bbox.Max.X, bbox.Max.Y, bbox.Max.Z)
                #     # outline = self.DB.Outline(minPoint, maxPoint)
                #     outline = self.DB.Outline(bbox.Min, bbox.Max)
                #     bboxFilters.Add(self.DB.BoundingBoxIntersectsFilter(outline))
                # bboxIntersectsOrFilter = self.DB.LogicalOrFilter(bboxFilters)
                # clashCollector.WherePasses(bboxIntersectsOrFilter)

                bbox = element.Geometry[options].GetBoundingBox()
                # tolerance = [x / 304.8 for x in tolerance]
                # minPoint = self.DB.XYZ(bbox.Min.X - tolerance[1], bbox.Min.Y - tolerance[2], bbox.Min.Z - abs(tolerance[0]))
                # maxPoint = self.DB.XYZ(bbox.Max.X + tolerance[1], bbox.Max.Y + tolerance[2], bbox.Max.Z + abs(tolerance[3]))
                minPoint = self.DB.XYZ(bbox.Min.X, bbox.Min.Y, bbox.Min.Z)
                maxPoint = self.DB.XYZ(bbox.Max.X, bbox.Max.Y, bbox.Max.Z)
                outline = self.DB.Outline(minPoint, maxPoint)
                #clashCollector.WherePasses(self.DB.LogicalOrFilter(self.DB.BoundingBoxIntersectsFilter(outline),self.DB.BoundingBoxIsInsideFilter(outline)))
                clashCollector.WherePasses(self.DB.BoundingBoxIntersectsFilter(outline))
                #clashCollector.WherePasses(self.DB.BoundingBoxIsInsideFilter(outline))

                if self.insulationFilter.PassesFilter(element):
                    if self.HOST_APP.version >= "2022":
                        parameter = element.GetParameter(self.DB.ParameterTypeId.RbsSystemNameParam)
                    else:
                        parameter = element.get_Parameter(self.DB.BuiltInParameter.RBS_SYSTEM_NAME_PARAM)
                    if parameter != None:
                        systemName = parameter.AsString()
                        if systemName != None:
                            clashCollector.WherePasses(
                                self.DB.ElementParameterFilter(
                                    self.DB.FilterStringRule(
                                        self.DB.ParameterValueProvider(
                                            parameter.Id
                                        ),
                                        self.DB.FilterStringEquals(),
                                        systemName,
                                        False
                                    ), True
                                )
                            )

                # clashCollector.WherePasses(self.DB.ElementIntersectsElementFilter(element))

                intersectsFilters = self.framework.System.Collections.Generic.List[self.DB.ElementFilter]()
                for geom in elementGeometry:
                    intersectsFilters.Add(self.DB.ElementIntersectsSolidFilter(geom))
                intersectsOrFilter = self.DB.LogicalOrFilter(intersectsFilters)
                clashCollector.WherePasses(intersectsOrFilter)

                # if clashCollector.GetElementCount() < 1:
                #     return

                # if not isBasicGeometry:
                #     elementGeometry = self.GetBasicElementGeometry(element, options)
                
                #n = "Apply collector: " + str(elementIdValue)
                with self.Timer("Apply collector"):
                    clashCollectorElements = clashCollector.ToElements()

                if clashCollectorElements.Count < 1:
                    continue

                collectorIds = []
                """Provision for Voids ausfindig machen"""
                for clashObject in clashCollectorElements:
                    collectorIds.append(clashObject.Id.IntegerValue)
                    attr = getattr(clashObject, "Symbol", None)
                    if attr == None:
                        continue
                    ifcParameters = self.framework.System.Collections.Generic.List[self.DB.Parameter]()
                    ifcParameters.AddRange(clashObject.GetParameters("IfcExportAs"))
                    ifcParameters.AddRange(clashObject.Symbol.GetParameters("IfcExportAs"))
                    isProvisionForVoid = False
                    for ifcParameter in ifcParameters:
                        if str(ifcParameter.AsString()).upper() == "PROVISIONFORVOID":
                            isProvisionForVoid = True
                    familyName = str(clashObject.Symbol.FamilyName)
                    if "VOID" in familyName.upper() and "PROVISION" in familyName.upper():
                        isProvisionForVoid = True
                    if not isProvisionForVoid:
                        continue
                    #self.alerts["pfv"] = "found"
                    provisionForVoids.Add(clashObject)
                    # ifcParameter = clashObject.Symbol.get_Parameter(self.framework.System.Guid("f53d1285-ae3d-4992-a3f1-2e7978be529a"))
                    # if ifcParameter == None:
                    #     continue
                    # ifcParameterValue = ifcParameter.AsString()
                    # if not isinstance(ifcParameterValue,str):
                    #     continue
                    # if ifcParameterValue.upper() == "PROVISIONFORVOID":
                    #     provisionForVoids.Add(clashObject)

                #self.alerts["pfv"] = []
                #self.alerts[element.Id.IntegerValue] = []
                method = self.GenerateTransientDisplayMethod() 

                for clashObject in clashCollectorElements:
                    #self.alerts[element.Id.IntegerValue].append(clashObject.Id.IntegerValue)
                    if clashObject.IsTransient:
                        continue

                    isProvisionForVoid = False
                    for pfv in provisionForVoids:
                        if clashObject.Id.IntegerValue == pfv.Id.IntegerValue:
                            isProvisionForVoid = True
                            break
                    if isProvisionForVoid:
                        continue

                    attr = getattr(clashObject, "SuperComponent", None)
                    if attr is not None:
                        if clashObject.SuperComponent.Id.IntegerValue in collectorIds:
                            continue
                    if elementIdValue < clashObject.Id.IntegerValue:
                        clashKey = str(elementIdValue) + "_" + str(clashObject.Id.IntegerValue)
                    else:
                        clashKey = str(clashObject.Id.IntegerValue) + "_" + str(elementIdValue)
                    
                    # if "clashkeys" not in self.alerts:
                    #     self.alerts["clashkeys"] = []
                    # self.alerts["clashkeys"].append(clashKey)

                    tolerance = (0,0,0,0)
                    clashObjectGeometry = self.GetBasicElementGeometry(clashObject, options, tolerance)
                    if clashObjectGeometry.Count == 0:
                        continue
                    #clashObjectGeometry = self.GetElementGeometry(clashObject, options)

                    geometryList = self.framework.System.Collections.Generic.List[self.DB.GeometryObject]()
                    for clashOjectGeometryIndex in range(clashObjectGeometry.Count-1, -1, -1):
                        for geom in elementGeometry:
                            try:
                                solid = self.DB.BooleanOperationsUtils.ExecuteBooleanOperation(
                                    geom,
                                    clashObjectGeometry.Item[clashOjectGeometryIndex],
                                    self.DB.BooleanOperationsType.Intersect)
                            except Exception as e:
                                """Minimal verschieben und noch mal probieren"""
                                try:
                                    transform = self.DB.Transform.CreateTranslation(self.DB.XYZ(0.001,0.001,0.001))
                                    solid = self.DB.BooleanOperationsUtils.ExecuteBooleanOperation(
                                        self.DB.SolidUtils.CreateTransformed(geom, transform),
                                        clashObjectGeometry.Item[clashOjectGeometryIndex],
                                        self.DB.BooleanOperationsType.Intersect)
                                except Exception as e:
                                    #self.alerts[e] = ""
                                    continue
                            if not solid.Volume > 0:
                                continue
                            geometryList.Add(solid)
                    
                    if geometryList.Count < 1:
                        continue

                    clashGeometries.Add(geometryList)
                    clashKeys.Add(clashKey)

            for geometryList, clashKey in zip(clashGeometries, clashKeys):
                for provisionForVoid in provisionForVoids:
                    provisionForVoidGeo = self.GetBasicElementGeometry(provisionForVoid, options)
                    
                    combinedprovisionForVoidGeo = provisionForVoidGeo.Item[0]
                    for geom in provisionForVoidGeo:
                        combinedprovisionForVoidGeo = self.DB.BooleanOperationsUtils.ExecuteBooleanOperation(
                            combinedprovisionForVoidGeo,
                            geom,
                            self.DB.BooleanOperationsType.Union)
                            
                    for geometryIndex in range(geometryList.Count-1, -1, -1):
                        #self.alerts["pfv"].append("test")
                        try:
                            solid = self.DB.BooleanOperationsUtils.ExecuteBooleanOperation(
                                geometryList[geometryIndex],
                                combinedprovisionForVoidGeo,
                                self.DB.BooleanOperationsType.Difference)
                        except Exception as e:
                            try:
                                transform = self.DB.Transform.CreateTranslation(self.DB.XYZ(0.001,0.001,0.001))
                                solid = self.DB.BooleanOperationsUtils.ExecuteBooleanOperation(
                                    self.DB.SolidUtils.CreateTransformed(geometryList[geometryIndex], transform),
                                    combinedprovisionForVoidGeo,
                                    self.DB.BooleanOperationsType.Intersect)
                            except Exception as e:
                                #self.alerts["pfv"].append(e)
                                continue
                        if not solid.Volume > 0:
                            geometryList.RemoveAt(geometryIndex)
                            continue
                        geometryList.RemoveAt(geometryIndex)
                        geometryList.Add(solid)

                if geometryList.Count < 1:
                    continue
                
                #solid = self.CreateSolidFromBoundingBox(bbox)
                #geometryList.Add(solid)
                # for geo in clashObjectGeometry:
                #     geometryList.Add(geo)

                #method = self.GenerateTransientDisplayMethod()
                argsM = self.framework.System.Array.CreateInstance(self.framework.System.Object, 4)
                argsM[0] = self.doc
                argsM[1] = self.DB.ElementId.InvalidElementId
                argsM[2] = geometryList
                #argsM[2] = elementGeometry
                #argsM[2] = clashObjectGeometry
                #argsM[3] = graphicsStyle.Id
                argsM[3] = self.DB.ElementId.InvalidElementId
                #argsM[3] = self.style.Id
                transientElementId = method.Invoke(None, argsM)
                if clashKey not in self.transientElementIds:
                    self.transientElementIds[clashKey] = []
                self.transientElementIds[clashKey].append(transientElementId)

                # argsM = self.framework.System.Array.CreateInstance(self.framework.System.Object, 4)
                # argsM[0] = self.doc
                # argsM[1] = self.DB.ElementId.InvalidElementId
                # argsM[2] = clashObjectGeometry
                # argsM[3] = self.DB.ElementId.InvalidElementId
                # transientElementId = method.Invoke(None, argsM)
                # self.transientElementIds[elementIdValue].append(transientElementId)

                # directShape = self.DB.DirectShape.CreateElement(self.doc, self.DB.ElementId(self.DB.BuiltInCategory.OST_ElectricalEquipment))
                # isValid = directShape.IsValidShape(geometryList)
                # if isValid == False:
                #     for index in range(geometryList.Count-1, -1, -1):
                #         if not isinstance(geometryList[index], self.DB.Solid):
                #             continue
                #         isValid = directShape.IsValidGeometry(geometryList[index])
                #         if not isValid:
                #             geometryList.RemoveAt(index)

                # directShape.SetShape(geometryList)
                # directShape.SetName(clashKey)

        except:
            self.PrintException()

    def GetElementGeometry(self, element, options, geometry=None):
        try:
            initial = False
            if geometry == None:
                geometry = self.framework.System.Collections.Generic.List[self.DB.GeometryObject]()
                initial = True
            
            # attr = getattr(element, "GetSubComponentIds", None)
            # if attr is not None:
            #     for subElementId in element.GetSubComponentIds():
            #         subElement = self.doc.GetElement(subElementId)
            #         self.GetElementGeometry(subElement, options, geometry)

            elementGeometry = element.Geometry[options]
            for geo in elementGeometry:
                if isinstance(geo, self.DB.GeometryInstance):
                    for subGeo in geo.GetInstanceGeometry():
                        if not isinstance(subGeo, self.DB.Solid):
                            continue
                        if subGeo.Volume == 0:
                            continue
                        if subGeo.Faces.Size < 0:
                            continue
                        gStyle = self.doc.GetElement(subGeo.GraphicsStyleId)
                        if gStyle != None:
                            if gStyle.GraphicsStyleCategory.Id.IntegerValue == self.DB.ElementId(self.DB.BuiltInCategory.OST_LightingFixtureSource).IntegerValue:
                                continue
                        if subGeo.Id == -1:
                            continue
                        geometry.Add(subGeo)
                        #self.alerts["stuff"].append(subGeo)
                    continue
                if not isinstance(geo, self.DB.Solid):
                    continue
                if geo.Volume == 0:
                    continue
                if geo.Faces.Size < 0:
                    continue
                gStyle = self.doc.GetElement(geo.GraphicsStyleId)
                if gStyle != None and gStyle.GraphicsStyleCategory.Id.IntegerValue == self.lightingFixtureSourceId:
                    continue
                geometry.Add(geo)
                #self.alerts["stuff"].append(geo)

            # if initial and geometry.Count > 1:
            #     solid = geometry.Item[0]
            #     for geo in geometry[1:]:
            #         solid = self.DB.BooleanOperationsUtils.ExecuteBooleanOperation(
            #             solid,
            #             geo,
            #             self.DB.BooleanOperationsType.Union)
            #     geometry = self.framework.System.Collections.Generic.List[self.DB.GeometryObject]()
            #     geometry.Add(solid)
            return geometry
        except:
            self.PrintException()

    #@timing
    def GetBasicElementGeometry(self, element, options, tolerance=(0,0,0,0)):
        try:
            """GetElementRotation"""
            if not isinstance(element.Location, self.DB.LocationCurve):
                tolerance = (0,0,0,0)
            geometry = self.GetElementGeometry(element, options)
            newGeometry = self.framework.System.Collections.Generic.List[self.DB.GeometryObject]()

            if self.insulationFilter.PassesFilter(element):
                #hostElement = self.doc.GetElement(element.HostElementId)
                element = element.Document.GetElement(element.HostElementId)

            if isinstance(element.Location, self.DB.LocationPoint):
                baseTransform = element.GetTransform()
                for solid in geometry:
                    transformedSolid = self.DB.SolidUtils.CreateTransformed(solid, baseTransform.Inverse)
                    bbox = transformedSolid.GetBoundingBox()
                    newSolid = self.CreateSolidFromBoundingBox(bbox, tolerance)
                    if newSolid == False:
                        continue
                    #newGeometry.Add(newSolid)
                    transformedSolid = self.DB.SolidUtils.CreateTransformed(newSolid, baseTransform)
                    newGeometry.Add(transformedSolid)
                    newGeometry.Add(transformedSolid)
            else:
                startPoint = element.Location.Curve.GetEndPoint(0)
                endPoint = element.Location.Curve.GetEndPoint(1)
                baseTransform = None
                try:
                    hashset = element.MEPModel.ConnectorManager.Connectors
                except:
                    try:
                        hashset = element.ConnectorManager.Connectors
                    except:			
                        hashset = []
                connectors = []
                for connector in hashset:
                    if connector.Origin.IsAlmostEqualTo(endPoint):
                        baseTransform = connector.CoordinateSystem
                if baseTransform != None:
                    for solid in geometry:
                        transformedSolid = self.DB.SolidUtils.CreateTransformed(solid, baseTransform.Inverse)
                        bbox = transformedSolid.GetBoundingBox()
                        newSolid = self.CreateSolidFromBoundingBox(bbox, tolerance)
                        if newSolid == False:
                            continue
                        #newGeometry.Add(newSolid)
                        transformedSolid = self.DB.SolidUtils.CreateTransformed(newSolid, baseTransform)
                        newGeometry.Add(transformedSolid)
                        newGeometry.Add(transformedSolid)
                else:
                    xRotation = 0
                    yRotation = 0
                    x = 0
                    y = 0
                    z = 0
                    count = geometry.Count
                    for geom in geometry:
                        xyz = geom.ComputeCentroid()
                        x += xyz.X
                        y += xyz.Y
                        z += xyz.Z
                    centroid = self.DB.XYZ(x/count, y/count, z/count)
                    elementVector = endPoint - startPoint
                    yRotation = elementVector.AngleTo(self.DB.XYZ.BasisZ)

                    elementVector = self.DB.XYZ(endPoint.X, endPoint.Y, startPoint.Z) - self.DB.XYZ(startPoint.X, startPoint.Y, startPoint.Z)
                    if endPoint.X > startPoint.X:
                        xRotation = elementVector.AngleTo(self.DB.XYZ.BasisY)
                    else:
                        xRotation = elementVector.AngleTo(self.DB.XYZ.BasisY)*-1
                    
                    xtransform = self.DB.Transform.CreateRotationAtPoint(self.DB.XYZ.BasisZ, xRotation, centroid)
                    ytransform = self.DB.Transform.CreateRotationAtPoint(self.DB.XYZ.BasisX, yRotation, centroid)
                    for solid in geometry:
                        xrotatedSolid = self.DB.SolidUtils.CreateTransformed(solid, xtransform)
                        yrotatedSolid = self.DB.SolidUtils.CreateTransformed(xrotatedSolid, ytransform)
                        bbox = yrotatedSolid.GetBoundingBox()
                        newSolid = self.CreateSolidFromBoundingBox(bbox, tolerance)
                        if newSolid == False:
                            continue
                        ytransformedSolid = self.DB.SolidUtils.CreateTransformed(newSolid, ytransform.Inverse)
                        xtransformedSolid = self.DB.SolidUtils.CreateTransformed(ytransformedSolid, xtransform.Inverse)
                        newGeometry.Add(xtransformedSolid)
                        newGeometry.Add(xtransformedSolid)

            return newGeometry
                
        except:
            if "Unknown Elements" not in self.alerts:
                self.alerts["Unknown Elements"] = []
            self.alerts["Unknown Elements"].append(element.Id)
            if isinstance(element, self.DB.DirectShape):
                self.doc.Delete(element.Id)
            self.PrintException()
    
    def CreateSolidFromBoundingBox(self, boundingBox, tolerance=(0,0,0,0)):
        try:
            tolerance = [x / 304.8 for x in tolerance]
            curves = self.framework.System.Collections.Generic.List[self.DB.Curve]()
            p1 = self.DB.XYZ(boundingBox.Min.X - tolerance[1], boundingBox.Min.Y - tolerance[0], boundingBox.Min.Z) # - tolerance[3]-0.01)
            p2 = self.DB.XYZ(boundingBox.Max.X + tolerance[2], boundingBox.Min.Y - tolerance[0], boundingBox.Min.Z) # - tolerance[3]-0.01)
            p3 = self.DB.XYZ(boundingBox.Max.X + tolerance[2], boundingBox.Max.Y + tolerance[3], boundingBox.Min.Z) # - tolerance[3]-0.01)
            p4 = self.DB.XYZ(boundingBox.Min.X - tolerance[1], boundingBox.Max.Y + tolerance[3], boundingBox.Min.Z) # - tolerance[3]-0.01)
            curves.Add(self.DB.Line.CreateBound(p1, p2))
            curves.Add(self.DB.Line.CreateBound(p2, p3))
            curves.Add(self.DB.Line.CreateBound(p3, p4))
            curves.Add(self.DB.Line.CreateBound(p4, p1))
            height = boundingBox.Max.Z - boundingBox.Min.Z # + tolerance[0] + tolerance[3] + 0.02
            # self.alerts["Height"] = height * 304.8
            loopList = self.framework.System.Collections.Generic.List[self.DB.CurveLoop]()
            loopList.Add(self.DB.CurveLoop.Create(curves))
            preTransformBox = self.DB.GeometryCreationUtilities.CreateExtrusionGeometry(loopList, self.DB.XYZ.BasisZ, abs(height), self.solidOptions)

            transformBox = self.DB.SolidUtils.CreateTransformed(preTransformBox, boundingBox.Transform)

            return transformBox

        # except self.Autodesk.Revit.Exceptions.ArgumentsInconsistentException:
        #     return False
        except Exception as e:
            if "ArgumentsInconsistentException" in str(type(e)):
                return False
            else:
                self.PrintException()

    def GenerateTransientDisplayMethod(self):
        try:
            #geometryElementType = self.framework.System.Type.GetType(self.DB.GeometryElement)
            geometryElementType = self.framework.clr.GetClrType(self.DB.GeometryElement)
            BindingFlags = self.framework.System.Reflection.BindingFlags
            geometryElementTypeMethods = geometryElementType.GetMethods(BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic)
            method = next((x for x in geometryElementTypeMethods if x.Name == "SetForTransientDisplay"), None)
            return method
        except:
            self.PrintException()

    class TransientElementFilter(DB.LogicalOrFilter):
        def __new__(self):
            return self
        def ElementPasses(self, element):
            if element.IsTransient:
                return True
            else:
                return False
        def PassesFilter(self, element):
            if element.IsTransient:
                return True
            else:
                return False

    def RefreshOnIdleHandler(self, sender, args):
        try:
            if len(self.customUpdaterData) > 0:# != None:
                for updaterDataIndex in range(len(self.customUpdaterData)-1, -1, -1):
                    self.Execute(self.customUpdaterData[updaterDataIndex])
                    self.customUpdaterData.pop(updaterDataIndex)
            return
        except Exception as e:
            print(self.traceback.format_exc())

    def DocChangeHandler(self, sender, args):
        try:
            if args.Operation == self.DB.Events.UndoOperation.TransactionUndone:
                self.customUpdaterData.append(self.CustomUpdaterData(self, args))
                return
            if args.Operation == self.DB.Events.UndoOperation.TransactionRedone:
                self.customUpdaterData.append(self.CustomUpdaterData(self, args))
                return
        except Exception as e:
            print(self.traceback.format_exc())

    class CustomUpdaterData():
        """Helper class to provide event args after their lifetime has run out"""
        def __init__(self, updater, args=None):
            self.updater = updater
            elementFilter = self.updater.DB.LogicalAndFilter(self.updater.mainCatFilter, self.updater.DB.ElementIsElementTypeFilter(True))
            if args != None:
                self._addedElementIds = args.GetAddedElementIds(elementFilter)
                self._modifiedElementIds = args.GetModifiedElementIds(elementFilter)
                self._deletedElementIds = args.GetDeletedElementIds()
                self._document = args.GetDocument()
            else:
                self._addedElementIds = updater.framework.System.Collections.Generic.List[object]()
                self._modifiedElementIds = updater.framework.System.Collections.Generic.List[object]()
                self._deletedElementIds = updater.framework.System.Collections.Generic.List[object]()
                self._document = updater.HOST_APP.doc
        def GetDocument(self):
            return self._document
        def GetAddedElementIds(self):
            return self._addedElementIds
        def GetModifiedElementIds(self):
            return self._modifiedElementIds
        def GetDeletedElementIds(self):
            return self._deletedElementIds

    #@timing
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

    def GetElementLocation(self, element):
        point = None
        try:
            point = element.Location.Curve.Evaluate(0.5, False)
        except:
            point = element.Location.Point
        if not point:
            return
        return point

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


CLASH_UPDATER_ENV_VAR = 'CLASH_UPDATER_ENV_VAR'
IDLING__HANDLER_ENV_VAR = 'IDLING__HANDLER_ENV_VAR'
DOC_CHANGED_HANDLER_ENV_VAR = 'DOC_CHANGED_HANDLER_ENV_VAR'

defaultCategories = framework.System.Collections.Generic.List[DB.BuiltInCategory]([
    DB.BuiltInCategory.OST_FireAlarmDevices,
    DB.BuiltInCategory.OST_CableTray,
    DB.BuiltInCategory.OST_CableTrayFitting,
    DB.BuiltInCategory.OST_CommunicationDevices,
    DB.BuiltInCategory.OST_Conduit,
    DB.BuiltInCategory.OST_ConduitFitting,
    DB.BuiltInCategory.OST_DataDevices,
    DB.BuiltInCategory.OST_Doors,
    DB.BuiltInCategory.OST_DuctAccessory,
    DB.BuiltInCategory.OST_DuctCurves,
    DB.BuiltInCategory.OST_DuctFitting,
    DB.BuiltInCategory.OST_ElectricalEquipment,
    DB.BuiltInCategory.OST_ElectricalFixtures,
    DB.BuiltInCategory.OST_LightingDevices,
    DB.BuiltInCategory.OST_LightingFixtures,
    DB.BuiltInCategory.OST_MechanicalEquipment,
    DB.BuiltInCategory.OST_PipeAccessory,
    DB.BuiltInCategory.OST_PipeCurves,
    DB.BuiltInCategory.OST_PipeFitting,
    DB.BuiltInCategory.OST_PipeInsulations,
    DB.BuiltInCategory.OST_SecurityDevices,
    DB.BuiltInCategory.OST_TelephoneDevices,
    DB.BuiltInCategory.OST_Walls
    ])

def registerUpdater(categories=defaultCategories, sender= None, args= None):
    try:
        catFilter = DB.ElementMulticategoryFilter(categories)
        
        updater = Updater(HOST_APP.addin_id, catFilter)
        DB.UpdaterRegistry.RegisterUpdater(updater)
        DB.UpdaterRegistry.SetIsUpdaterOptional(updaterId,True)
        DB.UpdaterRegistry.AddTrigger(updaterId, catFilter, DB.Element.GetChangeTypeElementDeletion())
        DB.UpdaterRegistry.AddTrigger(updaterId, catFilter, DB.Element.GetChangeTypeElementAddition())
        DB.UpdaterRegistry.AddTrigger(updaterId, catFilter, DB.Element.GetChangeTypeAny())
        #catsWithTrays = DB.LogicalOrFilter(catFilter, DB.ElementCategoryFilter(DB.BuiltInCategory.OST_CableTrayFitting))
        #DB.UpdaterRegistry.AddTrigger(updaterId, catsWithTrays, DB.Element.GetChangeTypeElementDeletion())

        script.set_envvar(CLASH_UPDATER_ENV_VAR, updater)

        handler = framework.System.EventHandler[DB.Events.DocumentChangedEventArgs](updater.DocChangeHandler)
        script.set_envvar(DOC_CHANGED_HANDLER_ENV_VAR, handler)
        HOST_APP.app.DocumentChanged += handler

        handler = framework.System.EventHandler[UI.Events.IdlingEventArgs](updater.RefreshOnIdleHandler)
        script.set_envvar(IDLING__HANDLER_ENV_VAR, handler)
        HOST_APP.uiapp.Idling += handler

        script.toggle_icon(True, icon_size=script.ICON_LARGE)

        return updater

    except Exception as e:
        print("Echtzeitpruefung: "+str(e))

def unregisterUpdater(sender = None, args = None):
    try:
        handler = script.get_envvar(DOC_CHANGED_HANDLER_ENV_VAR)
        HOST_APP.app.DocumentChanged -= handler

        handler = script.get_envvar(IDLING__HANDLER_ENV_VAR)
        HOST_APP.uiapp.Idling -= handler
        
        
        DB.UpdaterRegistry.RemoveAllTriggers(updaterId)
        DB.UpdaterRegistry.UnregisterUpdater(updaterId)
        
        transientElementIds = script.get_envvar("transientElementIds")
        doc = HOST_APP.doc
        transaction = DB.Transaction(doc, "Kollisionskörper Löschen")
        transaction.Start()
        for clashKey in transientElementIds.copy():
            for index, tId in reversed(list(enumerate(transientElementIds[clashKey]))):
                try:
                    transientElement = doc.GetElement(tId)
                    if transientElement.IsTransient:
                        doc.Delete(tId)
                        del transientElementIds[clashKey][index]
                except Exception as e:
                    pass
                    #print(e)
            del transientElementIds[clashKey]
        transaction.Commit()
        script.toggle_icon(False, icon_size=script.ICON_LARGE)
        #print("Updater Unregistered")
    except Exception as e:
        print("Echtzeitpruefung: "+str(e))
        transaction.RollBack()

def checkForAutomaticActivation(sender = None, args = None):
    try:
        ui_button_cmp = script.get_envvar("REALTIMECLASHBUTTON")
        script_cmp = script.get_envvar("REALTIMECLASHSCRIPT")
        event_doc = sender.ActiveUIDocument.Document
        if not isinstance(event_doc, DB.Document):
            if DB.UpdaterRegistry.IsUpdaterRegistered(updaterId):
                #unregisterUpdater()
                #ui_button_cmp.set_icon(script_cmp.directory+"\\off.png", 32)
                pass
            return
            #raise Exception("Zero Doc")
        globalParamId = DB.GlobalParametersManager.FindByName(event_doc,"TGA_Clash-Konfiguration")
        if globalParamId.IntegerValue == -1:
            if DB.UpdaterRegistry.IsUpdaterRegistered(updaterId):
                #unregisterUpdater()
                #ui_button_cmp.set_icon(script_cmp.directory+"\\off.png", 32)
                pass
            return
            #raise Exception("Missing config")
        globalParam = event_doc.GetElement(globalParamId)
        globalParamValue = globalParam.GetValue().Value

        config = {}
        try:
            config = json.loads(globalParamValue)
        except:
            if DB.UpdaterRegistry.IsUpdaterRegistered(updaterId):
                #unregisterUpdater()
                #ui_button_cmp.set_icon(script_cmp.directory+"\\off.png", 32)
                pass

        if "UpdaterActive" not in config:
            return

        if config["UpdaterActive"] == True:
            if not DB.UpdaterRegistry.IsUpdaterRegistered(updaterId):
                registerUpdater()
                ui_button_cmp.set_icon(script_cmp.directory+"\\on.png", 32)
    except Exception as e:
        try:
            forms.alert(str(traceback.format_exc()))
        except:
            print(str(e))
        return

class VmCategorie(forms.Reactive):
    def __init__(self, name, category, checked=False):
        self._name = name
        self._checked = checked
        self.category = category
    @forms.reactive
    def name(self):
        return self._name
    @name.setter
    def name(self, value):
        self._name = value
    @forms.reactive
    def checked(self):
        return self._checked
    @checked.setter
    def checked(self, value):
        self._checked = value

class VmLink(forms.Reactive):
    def __init__(self, name, linkInstanceId, checked=False, enabled=True):
        self._name = name
        self.linkInstanceId = linkInstanceId
        self._checked = checked
        self.enabled = enabled
    @forms.reactive
    def name(self):
        return self._name
    @name.setter
    def name(self, value):
        self._name = value
    @forms.reactive
    def checked(self):
        return self._checked
    @checked.setter
    def checked(self, value):
        self._checked = value

class ViewModel(forms.Reactive):
    def __init__(self):
        self.doc = HOST_APP.doc
        self.framework = framework
        #self.vmParameter = vmParameter

        self.strictSearch = False
        self.searchInput = ""
        self.allCategories = []
        self.visibleCategories = framework.ObservableCollection[VmCategorie]()
        self.selectedCategories = framework.System.Collections.Generic.List[DB.ElementId]()
        self.links = framework.ObservableCollection[VmLink]()

    def refreshSearch(self):
        self.visibleCategories.Clear()
        for cat in self.allCategories:
            if cat.name.upper().startswith(self.searchInput.upper()):
                self.visibleCategories.Add(cat)
        for cat in self.allCategories:
            if self.visibleCategories.Contains(cat):
                continue
                pass
            if self.searchInput.upper() in cat.name.upper():
                self.visibleCategories.Add(cat)
        if not self.strictSearch:
            for cat in self.allCategories:
                if self.visibleCategories.Contains(cat):
                    #continue
                    pass
                cont = False
                catName = cat.name.upper()
                for s in self.searchInput.upper():
                    if s in catName:
                        catName = catName[catName.index(s):]
                    else:
                        cont = True
                if cont:
                    continue
                self.visibleCategories.Add(cat)

class Window(forms.WPFWindow, forms.Reactive):
    def __init__(self):
        try:
            self.doc = HOST_APP.doc
            self.HOST_APP = HOST_APP
            self.vm = ViewModel()
            self.DB = DB
            self.framework = framework
            self.traceback = traceback
            self.time = time
            self.updater = None
        except:
            print(self.traceback.format_exc())

    def setup(self):
        try:
            self.typeTimer = self.time.time()
            self.typedText = ""
            self.CatBox.DataContext = self.vm
            
            modelCategories = {}
            for x in self.doc.Settings.Categories:
                if x.CategoryType != DB.CategoryType.Model: continue
                if not x.IsVisibleInUI: continue
                if not x.AllowsBoundParameters: continue
                if not x.AllowsVisibilityControl: continue
                modelCategories[x.Name] = x

                vmcat = VmCategorie(x.Name, x)
                self.vm.allCategories.append(vmcat)

            self.vm.allCategories.sort(key=lambda x: x.name)

            self.vm.refreshSearch()

            # for catName in sorted(modelCategories):
            #     vmcat = VmCategorie(catName, modelCategories[catName])
            #     for defaultCat in defaultCategories:
            #         if modelCategories[catName].Id.IntegerValue == self.DB.ElementId(defaultCat).IntegerValue:
            #             vmcat.checked = True
            #     self.vm.allCategories.append(vmcat)

            #self.MainGrid.DataContext = Window
            
            if DB.UpdaterRegistry.IsUpdaterRegistered(updaterId):
                self.UpdaterStatusBox.Content = "Echtzeitprüfung Aktiv"
                self.UpdaterStatusBox.IsChecked = True

            self.LinkBox.DataContext = self.vm
            linkCollector = DB.FilteredElementCollector(self.doc)
            linkCollector.OfClass(DB.RevitLinkInstance)

            self.vm.links.Add(VmLink("<Aktuelles Modell>", -1, checked=True, enabled=False))
            for link in linkCollector:
                linkdoc = link.GetLinkDocument()
                if linkdoc == None:
                    continue
                if HOST_APP.version >= "2022":
                    parameter = link.GetParameter(DB.ParameterTypeId.RvtLinkInstanceName)
                else:
                    parameter = link.get_Parameter(DB.BuiltInParameter.RVT_LINK_INSTANCE_NAME)
                linkName = parameter.AsString()
                self.vm.links.Add(VmLink(str(linkName)+" - "+linkdoc.Title, link.Id.IntegerValue))

            self.defaultCategories = [self.DB.ElementId(builtInCat).IntegerValue for builtInCat in defaultCategories]

            self.checkConfig()
            
            self.CategoriesChanged()

        except:
            print(self.traceback.format_exc())

    def CategoriesChanged(self, sender=None, args=None):
        try:
            count = 0
            for item in self.vm.allCategories:
                if item.checked:
                    count += 1
            self.selectedCatCount.Text = str(count)
            # if DB.UpdaterRegistry.IsUpdaterRegistered(updaterId):
            #     unregisterUpdater()
            #     self.UpdaterStatusBox.IsChecked = False
            #     self.UpdaterStatusBox.Content = "Echtzeitprüfung Inaktiv (Updater muss neu gestartet werden um die Änderungen zu übernehmen)"
            #self.vm.updateParas()

            # self.vm.elements.Clear()
            # eFilter = self.DB.ElementMulticategoryFilter(self.vm.selectedCats)
            # collector = self.DB.FilteredElementCollector(doc).WhereElementIsNotElementType().WherePasses(eFilter)
            # for ele in collector:
            #     self.vm.elements.Add(vmElement(ele))
        except:
            print(self.traceback.format_exc())


    def updateCategories(self, sender, args):
        try:
            self.vm.searchInput = self.catSearch.Text
            self.vm.refreshSearch()
            #self.vm.visibleCategories
        except:
            print(self.traceback.format_exc())
    
    def SelectAllCats(self, sender, args):
        for item in self.vm.visibleCategories:
            item._checked = True
        self.vm.refreshSearch()
        self.CategoriesChanged()

    def SelectNoCats(self, sender, args):
        for item in self.vm.allCategories:
            item._checked = False
        self.vm.refreshSearch()
        self.CategoriesChanged()

    def checkConfig(self, sender=None, args=None):
        try:

            self.usercfg = script.get_config("KOO")

            if not self.usercfg.has_option("categories"):
                self.usercfg.set_option("categories", [])
                script.save_config()

            if self.usercfg.categories == []:
                for cat in self.vm.allCategories:
                    if cat.category.Id.IntegerValue in self.defaultCategories:
                        cat.checked = True

            for cat in self.vm.allCategories:
                if cat._name in self.usercfg.categories:
                    cat.checked = True

            #cfgCategories = [cat._name for cat in self.vm.allCategories if cat._checked]

            #usercfg.categories = cfgCategories

            # for defaultCat in defaultCategories:
            # if modelCategories[catName].Id.IntegerValue == self.DB.ElementId(defaultCat).IntegerValue:

            if not self.usercfg.has_option("links"):
                self.usercfg.set_option("links", {})
                script.save_config()

            cfgLinks = self.usercfg.links

            projectId = str(self.HOST_APP.doc.ProjectInformation.UniqueId)

            if projectId in cfgLinks:
                # cfgLinks[projectId] = []
                # self.usercfg.set_option("links", cfgLinks)
                # script.save_config()

                for vmLink in self.vm.links:
                    strId = str(vmLink.linkInstanceId)
                    if strId in cfgLinks[projectId]:
                        vmLink._checked = True

                # if strId in cfgLinks[projectId]:
                #     vmlink.checked = cfgLinks[projectId][strId]["Enabled"]

            # self.usercfg.set_option("links", cfgLinks)


            # try:
            #     usercfg.get_option("categories")
            #     usercfg.get_option("links")
            # except:
            #     pass

            # globalParamId = DB.GlobalParametersManager.FindByName(HOST_APP.doc,"TGA_Clash-Konfiguration")
            # self.globalParam = False
            # if globalParamId.IntegerValue != -1:
            #     self.globalParam = HOST_APP.doc.GetElement(globalParamId)
                
            # self.config = {"Links":[], "Categories":[]}
            # try:
                # globalParamValue = self.globalParam.GetValue().Value
                # config = json.loads(globalParamValue)
            #     self.config = config # Seperated to catch the exception before writing self.config
            # except:
            #     pass

            # for linkInstanceId in self.config["Links"]:
            #     for vmlink in self.vm.links:
            #         if linkInstanceId == str(vmlink.linkInstanceId):
            #             vmlink.checked = self.config["Links"][linkInstanceId]["Enabled"]
            #             break

            # for catIntegerId in self.config["Categories"]:
            #     for vmcat in self.vm.categories:
            #         if catIntegerId == str(vmcat.category.Id.IntegerValue):
            #             vmcat.checked = self.config["Categories"][catIntegerId]["Enabled"]
            #             break

            
        except Exception as e:
            print(self.traceback.format_exc())

    def toggleCheckbox(self, sender=None, args=None):
        try:
            if sender.IsChecked:
                if not DB.UpdaterRegistry.IsUpdaterRegistered(updaterId):
                    cats = self.framework.System.Collections.Generic.List[DB.ElementId]()
                    for vmcat in self.vm.allCategories:
                        if vmcat.checked:
                            cats.Add(vmcat.category.Id)
                    self.updater = registerUpdater(cats)
                self.UpdaterStatusBox.Content = "Echtzeitprüfung Aktiv"
            if not sender.IsChecked:
                if DB.UpdaterRegistry.IsUpdaterRegistered(updaterId):
                    unregisterUpdater()
                self.UpdaterStatusBox.Content = "Echtzeitprüfung Inaktiv"
            pass
        except Exception as e:
            print(self.traceback.format_exc())
            #print("Echtzeitpruefung: "+str(e))

    def ListBox_PreviewKeyDown(self, sender, args):
        try:
            if not sender.IsKeyboardFocusWithin:
                return
            
            if self.time.time() - self.typeTimer > 1:
                self.typedText = ""

            if self.typedText == "" and args.Key == self.framework.System.Windows.Input.Key.Space:
                sender.SelectedItem.checked = not sender.SelectedItem.checked
                return
            
            self.typeTimer = self.time.time()

            self.typedText += args.Key.ToString().lower()

            #print(self.typedText)

            for item in self.vm.visibleCategories:
                if item.name.lower().startswith(self.typedText):
                    sender.SelectedItem = item
                    sender.ScrollIntoView(item)
                    break


        except:
            print(self.traceback.format_exc())


    def confirmAndCheck(self, sender = None, args = None):
        try:
            for vmLink in self.vm.links:
                if vmLink.checked:
                    pass
            if self.DB.UpdaterRegistry.IsUpdaterRegistered(updaterId):
                updater = script.get_envvar(CLASH_UPDATER_ENV_VAR)
                categories = self.framework.System.Collections.Generic.List[DB.ElementId]()
                for vmCat in self.vm.allCategories:
                    if vmCat.checked:
                        categories.Add(vmCat.category.Id)
                catFilter = DB.ElementMulticategoryFilter(categories)
                updater.mainCatFilter = catFilter

                initialCollector = self.DB.FilteredElementCollector(self.doc, self.HOST_APP.active_view.Id)
                initialCollector.WhereElementIsNotElementType()
                initialCollector.WherePasses(catFilter)

                updater = script.get_envvar(CLASH_UPDATER_ENV_VAR)
                cstomUpdaterData = updater.CustomUpdaterData(updater)
                cstomUpdaterData._modifiedElementIds = initialCollector.ToElementIds()
                updater.customUpdaterData.append(cstomUpdaterData)

            config = {"Links":{}, "Categories":{}}
            for vmLink in self.vm.links:
                config["Links"][str(vmLink.linkInstanceId)] = {"Name": vmLink.name, "Enabled":vmLink.checked}
            for vmCat in self.vm.allCategories:
                config["Categories"][str(vmCat.category.Id.IntegerValue)] = {"Name": vmCat.name, "Enabled":vmCat.checked}
            config["UpdaterActive"] = self.UpdaterStatusBox.IsChecked

            jsonString = json.dumps(config, ensure_ascii=False)
            paraValue = DB.StringParameterValue(jsonString)
            transaction = DB.Transaction(HOST_APP.doc, "Echtzeitprüfung Konfiguration Speichern")
            transaction.Start()
            try:
                if self.globalParam == False:
                    if HOST_APP.version >= "2022":
                        self.globalParam = DB.GlobalParameter.Create(HOST_APP.doc, "TGA_Clash-Konfiguration", DB.SpecTypeId.String.MultilineText)
                    else:
                        self.globalParam = DB.GlobalParameter.Create(HOST_APP.doc, "TGA_Clash-Konfiguration", DB.ParameterType.MultilineText)
                self.globalParam.SetValue(paraValue)
                transaction.Commit()
            except:
                transaction.RollBack()
                print(self.traceback.format_exc())

            self.Close()
        except Exception as e:
            print(self.traceback.format_exc())

    def confirmAndClose(self, sender = None, args = None):
        try:
            for vmLink in self.vm.links:
                if vmLink.checked:
                    pass
            if self.DB.UpdaterRegistry.IsUpdaterRegistered(updaterId):
                updater = script.get_envvar(CLASH_UPDATER_ENV_VAR)
                categories = self.framework.System.Collections.Generic.List[DB.ElementId]()
                for vmCat in self.vm.allCategories:
                    if vmCat.checked:
                        categories.Add(vmCat.category.Id)
                catFilter = DB.ElementMulticategoryFilter(categories)
                updater.mainCatFilter = catFilter

                # initialCollector = self.DB.FilteredElementCollector(self.doc)
                # initialCollector.WhereElementIsNotElementType()
                # initialCollector.WherePasses(catFilter)

                # updater = script.get_envvar(CLASH_UPDATER_ENV_VAR)
                # cstomUpdaterData = updater.CustomUpdaterData(updater)
                # cstomUpdaterData._modifiedElementIds = initialCollector.ToElementIds()
                # updater.customUpdaterData.append(cstomUpdaterData)


            cfgCategories = [cat._name for cat in self.vm.allCategories if cat._checked]

            self.usercfg.categories = cfgCategories

            projectId = self.HOST_APP.doc.ProjectInformation.UniqueId
            cfgLinks = self.usercfg.links


            if projectId not in cfgLinks:
                cfgLinks[projectId] = []
                self.usercfg.set_option("links", cfgLinks)

            for vmLink in self.vm.links:
                strId = str(vmLink.linkInstanceId)
                if strId == "-1":
                    continue
                #cfgLinks[projectId][str(vmLink.linkInstanceId)] = {"Name": vmLink.name, "Enabled":vmLink.checked}
                if vmLink.checked:
                    if strId not in cfgLinks[projectId]:
                        cfgLinks[projectId].append(strId)
                elif strId in cfgLinks[projectId]:
                    cfgLinks[projectId].remove(strId)

            if cfgLinks[projectId] == []:
                cfgLinks.pop(projectId)

            self.usercfg.links = cfgLinks


            script.save_config()
            # config = {"Links":{}, "Categories":{}}
            # for vmLink in self.vm.links:
            #     config["Links"][str(vmLink.linkInstanceId)] = {"Name": vmLink.name, "Enabled":vmLink.checked}

            # config["UpdaterActive"] = self.UpdaterStatusBox.IsChecked


            # jsonString = json.dumps(config, ensure_ascii=False)
            # paraValue = DB.StringParameterValue(jsonString)
            # transaction = DB.Transaction(HOST_APP.doc, "Echtzeitprüfung Konfiguration Speichern")
            # transaction.Start()
            # try:
            #     if self.globalParam == False:
            #         if HOST_APP.version >= "2022":
            #             self.globalParam = DB.GlobalParameter.Create(HOST_APP.doc, "TGA_Clash-Konfiguration", DB.SpecTypeId.String.MultilineText)
            #         else:
            #             self.globalParam = DB.GlobalParameter.Create(HOST_APP.doc, "TGA_Clash-Konfiguration", DB.ParameterType.MultilineText)
            #     self.globalParam.SetValue(paraValue)
            #     transaction.Commit()
            # except:
            #     transaction.RollBack()
            #     print(self.traceback.format_exc())

            self.Close()
        except Exception as e:
            print(self.traceback.format_exc())

    def onClosed(self, sender, args):
        try:
            pass
        except:
            print(self.traceback.format_exc())


updaterId = DB.UpdaterId(HOST_APP.addin_id, framework.System.Guid("c86f6253-c1fb-4a46-9d68-b7994e71d992"))

def __selfinit__(script_cmp, ui_button_cmp, __rvt__):
    """pyRevit smartbuttom init"""
    try:
        script.set_envvar("REALTIMECLASHBUTTON", ui_button_cmp)
        script.set_envvar("REALTIMECLASHSCRIPT", script_cmp)

        updaterId = DB.UpdaterId(HOST_APP.addin_id, framework.System.Guid("c86f6253-c1fb-4a46-9d68-b7994e71d992"))

        handler = framework.EventHandler[UI.Events.ViewActivatedEventArgs](checkForAutomaticActivation)
        __rvt__.ViewActivated += handler
        if DB.UpdaterRegistry.IsUpdaterRegistered(updaterId):
            ui_button_cmp.set_icon(script_cmp.directory+"\\on.png", script.ICON_LARGE)
        return True
    except:
        print(traceback.format_exc())
        return False

if __name__ == "__main__":
    window = script.load_ui(Window(), 'ui.xaml')
    # show modal or nonmodal
    window.show_dialog()
