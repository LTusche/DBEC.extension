# -*- coding=utf-8 -*-
#from pyrevit import UI, script, framework



# Tab-Namen von anderen Erweiterungen kürzen
if False:
    def shortenTabNames(sender, args):
        from pyrevit import script, AdWindows
        from pyrevit.api import AdWindows 
        ribbon = AdWindows.ComponentManager.Ribbon

        replaceList = {
            "MagiCAD" : "MC",
            "GENERATION" : "Gen"
        }

        for key in replaceList:
            l = [x for x in ribbon.Tabs if x.IsVisible and key in x.Title]
            for tab in l:
                tab.Title = tab.Title.replace(key, replaceList[key])

        handler = script.get_envvar('ShortenTabNamesHandler')
        __revit__.Idling -= handler


    handler = framework.EventHandler[UI.Events.IdlingEventArgs](shortenTabNames)
    __revit__.Idling += handler
    script.set_envvar('ShortenTabNamesHandler', handler)