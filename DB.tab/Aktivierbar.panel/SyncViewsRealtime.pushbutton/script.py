# -*- coding=utf-8 -*-
# import math

from pyrevit import framework, HOST_APP, script, UI

def copy_zoomstate(sender, args):
    try:
        import traceback
        import math
        from pyrevit import HOST_APP, script, DB
        SUPPORTED_VIEW_TYPES = (
            DB.ViewPlan,
            DB.ViewSection,
            DB.View3D,
            DB.ViewSheet,
            DB.ViewDrafting
        )

        ALLOWED_FLOORPLAN_VIEW_TYPES = [
            DB.ViewType.FloorPlan,
            DB.ViewType.CeilingPlan
        ]

        isactive = script.get_envvar('SYNCVIEWREALTIMEACTIVE') ### Context missing??
        if not isactive:
            return
        doc = HOST_APP.doc
        uidoc = HOST_APP.uidoc
        activeView = doc.ActiveView
        if not isinstance(activeView, SUPPORTED_VIEW_TYPES):
            return
        activeUiView = None
        for uv in uidoc.GetOpenUIViews():
            if uv.ViewId.Equals(activeView.Id):
                activeUiView = uv
                if activeView.ViewType == DB.ViewType.ThreeD:
                    orientation = activeView.GetOrientation()
                if activeView.ViewType == DB.ViewType.Section:
                    direction = activeView.ViewDirection
                break
        if activeUiView == None:
            return
        rect = activeUiView.GetZoomCorners()

        # Skip if current rectangle is the same as before
        cachedPoint = script.get_envvar('SYNCVIEWRECTANGLECACHE')
        if cachedPoint != None and cachedPoint.IsAlmostEqualTo(rect.Item[0]):
            return
        script.set_envvar('SYNCVIEWRECTANGLECACHE', rect.Item[0])

        for uiView in uidoc.GetOpenUIViews():
            # try:
            view = doc.GetElement(uiView.ViewId)

            if view.ViewType != activeView.ViewType and not (activeView.ViewType in ALLOWED_FLOORPLAN_VIEW_TYPES and view.ViewType in ALLOWED_FLOORPLAN_VIEW_TYPES):
                continue

            if uiView.ViewId.Equals(activeView.Id):
                continue

            if activeView.ViewType == DB.ViewType.ThreeD:
                view.SetOrientation(orientation)
            if activeView.ViewType == DB.ViewType.Section:
                angle = direction.AngleTo(view.ViewDirection)
                angle == 0 or int(angle*10**5) == int(0*10**5)
                if not (angle == math.pi or int(angle*10**5) == int(math.pi*10**5)) and not (angle == 0 or int(angle*10**5) == int(0*10**5)):
                    continue
            uiView.ZoomAndCenterRectangle(rect[0], rect[1])
            # except:
            #     continue

    except Exception as e:
        try:
            print(str(traceback.format_exc()))
        except:
            print(str(e))
        pass


def toggle_state():
    """Toggle tool state"""
    try:
        new_state = not script.get_envvar('SYNCVIEWREALTIMEACTIVE')
        
        if new_state:
            handler = framework.EventHandler[UI.Events.IdlingEventArgs](copy_zoomstate)
            HOST_APP.uiapp.Idling += handler
            #__revit__.Idling += handler
            script.set_envvar('SYNCVIEWREALTIMEHANDLER', handler)
        else:
            handler = script.get_envvar('SYNCVIEWREALTIMEHANDLER')
            HOST_APP.uiapp.Idling -= handler

        script.set_envvar('SYNCVIEWREALTIMEACTIVE', new_state)
        script.toggle_icon(new_state, icon_size=script.ICON_LARGE)
    except Exception as e:
        print(str(e))

if __name__ == '__main__':
    toggle_state()
