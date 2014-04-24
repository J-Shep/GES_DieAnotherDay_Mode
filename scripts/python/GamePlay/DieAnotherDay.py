from . import GEScenario
from GamePlay.Utils.GEPlayerTracker import GEPlayerTracker
from Utils.GETimer import TimerTracker, Timer

import GEPlayer, GEUtil, GEMPGameRules, GEGlobal, GEEntity

USING_API = GEGlobal.API_VERSION_1_1_1

'''
This mode is based on Mefy's MOHAA "Freeze Tag" Mode.

This mode script uses lots of code from the "You Only Live Twice" mode script.

The grave stones were created by Kraid.

Translators: 
 French: namajnaG,
 German: Kraid,
 Spanish: VGF
 Italian: Matteo Bini

Supported Languages: English,French,German,Spanish,Polish and Italian.

@author(s): Joe
@version: Alpha 1.10
'''
class DieAnotherDay(GEScenario):
    version = "Alpha 1.10 WIP"

    trEliminated = "eliminated"
    trSpawned = "spawned"

    maxDistanceBetweenGroundAndJumpingPlayer = 86.2 #46.00 jumping on ground   86.2 run and jump down Cradle stairs.
    maxDistanceBetweenGroundAndPlayerOrigin = 8.04

    #--------------- GUI Constants:
    mColour = GEUtil.CColor(0,150,255,255)
    jColour = GEUtil.Color(255,0,0,255)

    mRERadarColour = GEUtil.CColor(118,255,227,255) 
    mUsedRERadarColour= GEUtil.CColor(143,167,255,255)

    jRERadarColour = GEUtil.Color(255,118,118,255)
    jUsedRERadarColour= GEUtil.Color(255,80,39,255)

    RQPositionColour = GEUtil.Color(255,255,0,255)

    #Progress Bar Indexs
    resurrectionPBIndex = 2
    resBarY = 0.765
    resQueueMessageChannel = 3

    CVAR_RES_TIME = "dad_resTime"
    CVAR_USED_RE_REVEAL_TIME = "dad_usedRELocationRevealTime"

    def __init__( self ):
        super( DieAnotherDay, self ).__init__()

        self.resurrectionTime = 5 #Change with CVAR: dad_resTime
        self.usedRELocationRevealTime = 10 #Change with CVAR: dad_usedRELocationRevealTime

        self.radar = None
        self.timerTracker = TimerTracker(self)
        self.pltracker = GEPlayerTracker( self )
        self.tokenManager = GEMPGameRules.GetTokenMgr()
        self.HUDSCounts = DieAnotherDay.HUDSurvivorCounts()

        self.resurrections = DieAnotherDay.ResurrectionDict(self)
        self.REs = DieAnotherDay.REDict(self)

        self.playersLRRTargetMonitor = {}

        self.waitingForPlayers = False

        self.mResurrectionQueue = []
        self.jResurrectionQueue = []
        self.resurrectedPlayers = []

        self.eliminatedPlayerCount = 0

    def Cleanup( self ):
        super( DieAnotherDay, self ).Cleanup()
        self.resurrections.cleanup()
        self.REs.cleanup()
        self.resurrections = None
        self.REs = None
        self.pltracker = None
        self.timerTracker = None
        self.tokenManager = None
        self.radar = None
        self.mResurrectionQueue = None
        self.jResurrectionQueue = None
        self.playersLRRTargetMonitor = None
        self.resurrectedPlayers = None
    
    #1. Callback functions:
    def GetPrintName( self ):
        return "#GES_GP_DAD_NAME"
    
    def GetGameDescription( self ):
        return "#GES_GP_DAD_NAME"
    
    def GetScenarioHelp( self, help_obj ):
        help_obj.SetDescription( "#GES_GP_DAD_HELP" )
        
    def GetTeamPlay( self ):
        return GEGlobal.TEAMPLAY_ALWAYS
    
    def OnLoadGamePlay( self ):
        GEUtil.PrecacheModel("models/gameplay/gravestone.mdl")
        
        #TODO When the GE:S version after 4.2.3 is released with the nessecary translations, enable the use of these translations:
        self.CreateCVar(DieAnotherDay.CVAR_RES_TIME,"5","The duration of resurrections in DAD mode." )
        self.CreateCVar(DieAnotherDay.CVAR_USED_RE_REVEAL_TIME,"10","How long the location of a used grave stone will be shown to both sides.")
        
        self.radar = GEMPGameRules.GetRadar()
        self.radar.SetForceRadar(True)
    
    def OnCVarChanged( self, name, oldvalue, newvalue ):
        if name == DieAnotherDay.CVAR_RES_TIME:
            self.resurrectionTime = float(newvalue)
        elif name == DieAnotherDay.CVAR_USED_RE_REVEAL_TIME:
            self.usedRELocationRevealTime = float(newvalue)

    def OnPlayerConnect( self, player ):
        self.pltracker.SetValue(player,self.trSpawned,False)
        self.pltracker.SetValue(player,self.trEliminated,False)
        GEUtil.PopupMessage(player,"#GES_GP_DAD_NAME","#GES_GP_DAD_FIRST_SPAWN_INSTRUCTIONS")

    def OnPlayerDisconnect( self, player ):
        team = player.GetTeamNumber()

        if team != GEGlobal.TEAM_SPECTATOR and team != GEGlobal.TEAM_NONE:
            self.resurrections.playerHasDisconnected(player)
            wasEliminated = self.isEliminatedPlayer(player)

            if wasEliminated:
                self.OnEliminatedPlayerLeavesTeam(player,team)
                self.eliminatedPlayerCount -= 1

        if player in self.resurrectedPlayers: self.resurrectedPlayers.remove(player)

    def OnPlayerSay(self,player,text):
        if text == "!voodoo" or "!gesrocks":
            if not self.isEliminatedPlayer(player) and player.GetTeamNumber() != GEGlobal.TEAM_SPECTATOR:
                if not self.playersLRRTargetMonitor.has_key(player):
                    hitEntity = self.getEntHitByLRRLaser(player)
                    if hitEntity != None:
                        if hitEntity.GetClassname() == "ge_capturearea":
                            if hitEntity.GetTeamNumber() == player.GetTeamNumber() and self.REs.areaUsable(hitEntity):
                                self.beginREInteraction(player,hitEntity,False)

            return True

    def OnCaptureAreaSpawned( self, area ):
        areasTeam = area.GetTeamNumber()
        
        #Record that the RE area has been spawned
        self.REs.areaSpawned(area)
        
        #Add the RE's position to the radar.
        self.radar.AddRadarContact(area,GEGlobal.RADAR_TYPE_OBJECTIVE,True,"sprites/hud/radar/RE",self.getSidesRadarColour(areasTeam,True))
        
        #Setup radar icon for idle RE:
        self.radar.SetupObjective(area,areasTeam,"", "",self.getSidesColour(areasTeam),200,False)
        
        #If nesscary, move the spawned RE:
        ID = area.GetGroupName()
        if self.REs.needsToBeMoved(ID): self.REs.moveToDeathLocation(ID)
        
        #TODO Prevent 2 REs from overlapping
        #TODO Prevent RE from spawning in doorway.
        
    def OnCaptureAreaEntered(self,REArea,player,token):
        if REArea.GetTeamNumber() == player.GetTeamNumber() and self.REs.areaUsable(REArea): self.beginREInteraction(player,REArea,True)
        
    def OnCaptureAreaExited(self,REArea,player ):
        if REArea.GetTeamNumber() == player.GetTeamNumber(): self.resurrections.playerHasExitedFriendlyREArea(REArea,player)        

    def OnPlayerSpawn(self,player):
        self.pltracker.SetValue(player,self.trSpawned,True)
        GEUtil.HudMessage(player, "This unfinished DAD version is not meant to be played, it probably has bugs.",-1,-1, GEUtil.CColor(255, 0, 0,255),10.00,20)
        
        #Resurrected player respawns:
        if player in self.resurrectedPlayers: 
            self.resurrectedPlayers.remove(player)
        
        #A player spawns after joining a team:
        else:
            newTeam = player.GetTeamNumber()
            oldTeam = self.pltracker.GetValue(player,"team",-1)
            self.pltracker.SetValue(player,"team",newTeam)

    def OnPlayerObserver(self,player):
        self.pltracker.SetValue(player,self.trSpawned,False)
        
        currentTeam = player.GetTeamNumber()
        oldTeam = self.pltracker.GetValue(player,"team",-1)
        self.pltracker.SetValue(player,"team",player.GetTeamNumber())
        
        if currentTeam == GEGlobal.TEAM_SPECTATOR and (oldTeam == GEGlobal.TEAM_MI6 or oldTeam == GEGlobal.TEAM_JANUS):
            eliminatedBeforeObserver = self.isEliminatedPlayer(player)
            
            if eliminatedBeforeObserver: 
                self.OnEliminatedPlayerLeavesTeam(player,oldTeam)

    def observerTeamChangeCheck(self,timer,update_type,player):
        if update_type == Timer.UPDATE_FINISH and not GEMPGameRules.IsIntermission():
            currentTeam = player.GetTeamNumber()
            oldTeam = self.pltracker.GetValue(player,"team")
            self.pltracker.SetValue(player,"team",currentTeam)
            
            #Current team will be MI6/Janus:
            if currentTeam != oldTeam:
                if oldTeam == GEGlobal.TEAM_MI6 or oldTeam == GEGlobal.TEAM_JANUS:
                    self.OnEliminatedPlayerLeavesTeam(player,oldTeam)

                self.OnTeamHasNewEliminatedMember(player, None, None)
    
    def OnRoundEnd( self ):
        self.eliminatedPlayerCount = 0

        #End and delete all timers first to prevent post round reset timer callback errors:
        self.resurrections.cancelResurrections()
        for timer in self.timerTracker.timers: timer.Stop()
        self.timerTracker.RemoveTimer(None)
        
        #Reset everything else:
        self.REs.deleteAll()

        del self.resurrectedPlayers[:]
        del self.mResurrectionQueue[:]
        del self.jResurrectionQueue[:]
        
        self.radar.DropAllContacts()
    
    def OnRoundBegin( self ):
        self.HUDSCounts.show()

        if not self.waitingForPlayers:
            for i in range( 32 ):
                if not GEPlayer.IsValidPlayerIndex( i ):
                    continue
                self.pltracker.SetValue( GEPlayer.GetMPPlayer( i ), self.trEliminated, False )
    
            GEMPGameRules.ResetAllPlayerDeaths()
            GEMPGameRules.ResetAllPlayersScores()

        GEUtil.HudMessage(None, "This unfinished DAD version is not meant to be played, it probably has bugs.",-1,-1, GEUtil.CColor(255, 0, 0,255),10.00,20)

    def CanPlayerRespawn(self,player):
        notIntermission = not GEMPGameRules.IsIntermission()
        if not player in self.resurrectedPlayers:
            if self.isEliminatedPlayer(player) and notIntermission:
                return False
            elif self.eliminatedPlayerCount > 0 and notIntermission:
                self.OnPlayerEliminated(player)
                return False

        player.SetScoreBoardColor(GEGlobal.SB_COLOR_NORMAL)
        return True

    def OnPlayerKilled( self, victim, killer, weapon ):
        self.pltracker.SetValue(victim,self.trSpawned,False)

        killersTeam = None
        if killer: killersTeam = killer.GetTeamNumber()

        #If the player wasn't forced to commit suicide by changing their team:
        if(not self.pltracker.GetValue(victim,"CanPlayerChangeTeam()_called",False)):
            self.OnPlayerEliminated(victim,killer,weapon)

        #Change the killer's round score:
        if not victim:
            return
        if not killer or victim == killer:
            # World kill or suicide
            victim.AddRoundScore( -1 )
        elif killer.GetTeamNumber() == victim.GetTeamNumber():
            # Same-team kill
            killer.AddRoundScore( -1 )
        else:
            # Normal kill
            killer.AddRoundScore( 1 )

    '''
    This function is responsible for eliminating players and for responding to this event.
    '''
    def OnPlayerEliminated(self,victim,killer=None,weapon=None):
        team = victim.GetTeamNumber()
        #1.Eliminate the player:
        self.pltracker.SetValue(victim,self.trEliminated,True)
        self.eliminatedPlayerCount += 1
        #2. Cancel their resurrections:
        self.resurrections.playerHasBeenKilled(victim)

        #3. Announce the elimination:
        if killer != None:
            GEUtil.EmitGameplayEvent("DieAnotherDay_elimination",
                                     "%s" % victim.GetPlayerName(),
                                     "%i" % victim.GetTeamNumber(),
                                     "%s" % killer.GetPlayerName())
            if team == GEGlobal.TEAM_MI6:
                GEUtil.ClientPrint(None,GEGlobal.HUD_PRINTTALK, "#GES_GP_DAD_MI6_PLAYER_ELIMINATED", victim.GetPlayerName())
            else:
                GEUtil.ClientPrint(None,GEGlobal.HUD_PRINTTALK, "#GES_GP_DAD_JANUS_PLAYER_ELIMINATED", victim.GetPlayerName())

        #4. Change their scoreboard colour:
        victim.SetScoreBoardColor(GEGlobal.SB_COLOR_ELIMINATED)

        #If the round won't end because of this elimination:
        if GEMPGameRules.GetNumInRoundTeamPlayers(team) - 1 > 0:
            self.OnTeamHasNewEliminatedMember(victim,killer,weapon)

    def OnTeamHasNewEliminatedMember(self,player,killer,weapon):
        moveTo = self.decideWhereREWillBeLocated(player,killer,weapon)
        currentTeam = player.GetTeamNumber()
        self.REs.spawnNewResurrectionEntity(player,currentTeam,moveTo)
        self.addPlayerToResurrectionQueue(player,currentTeam)
        self.drawEliminatedPlayerResQueueMessage(player)

    def OnEliminatedPlayerLeavesTeam(self,player,team):        
        self.removePlayerFromTeamsRQueue(player,team)
        self.resurrections.deleteNotInUseRE(team)
        GEUtil.RemoveHudProgressBar(player, DieAnotherDay.resQueueMessageChannel)

    def OnThink(self):
        if not GEMPGameRules.IsIntermission():
            self.HUDSCounts.refresh(True)

        if GEMPGameRules.GetNumActivePlayers() < 2:
            self.waitingForPlayers = True
            return

        if self.waitingForPlayers:
            self.waitingForPlayers = False
            GEUtil.HudMessage( None, "#GES_GP_GETREADY", -1, -1, GEUtil.CColor( 255, 255, 255, 255 ), 2.5 )
            GEMPGameRules.EndRound( False )

        #Check to see if the round is over:
        #check to see if each team has a player...
        inPlayMPlayers = []
        inPlayJPlayers = []

        for i in range( 32 ):
            if not GEPlayer.IsValidPlayerIndex( i ):
                continue

            player = GEPlayer.GetMPPlayer( i )
            if self.IsInPlay( player ):
                if player.GetTeamNumber() == GEGlobal.TEAM_MI6:
                    inPlayMPlayers.append( player )
                elif player.GetTeamNumber() == GEGlobal.TEAM_JANUS:
                    inPlayJPlayers.append( player )

        numMI6Players = len(inPlayMPlayers)
        numJanusPlayers = len(inPlayJPlayers)

        if numMI6Players == 0 and numJanusPlayers == 0: GEMPGameRules.EndRound()
        elif numMI6Players == 0 and numJanusPlayers > 0: self.teamWins(GEGlobal.TEAM_JANUS)
        elif numMI6Players > 0 and numJanusPlayers == 0: self.teamWins(GEGlobal.TEAM_MI6)

    def teamWins(self,teamNumber):
        team = GEMPGameRules.GetTeam(teamNumber)
        team.SetRoundScore(1)
        GEMPGameRules.SetTeamWinner(team)
        GEMPGameRules.EndRound()
        
    def CanPlayerChangeTeam(self,player,oldTeam,newTeam):
        if oldTeam != GEGlobal.TEAM_SPECTATOR and newTeam != GEGlobal.TEAM_SPECTATOR and not self.isEliminatedPlayer(player):
            self.pltracker.SetValue(player,"CanPlayerChangeTeam()_called",True)
            def callback(timer,update_type):
                if update_type == Timer.UPDATE_FINISH:
                    self.pltracker.SetValue(player,"CanPlayerChangeTeam()_called",False)
            self.timerTracker.OneShotTimer(0.5,callback)

        if self.isEliminatedPlayer(player) and (newTeam == GEGlobal.TEAM_MI6 or newTeam == GEGlobal.TEAM_JANUS):
            teamChangeCheckTimer = DieAnotherDay.ExtCallbackTimer(self.timerTracker,self.observerTeamChangeCheck,player)
            teamChangeCheckTimer.start(1)
        return True
        
    #2. Info Getting Functions:
    @staticmethod
    def getEntHitByLRRLaser(user):
        traceEndVector = GEUtil.VectorMA(user.GetEyePosition(),user.GetAimDirection(),40000.00)
        return GEUtil.Trace(user.GetEyePosition(),traceEndVector,GEUtil.TraceOpt.CAPAREA | GEUtil.TraceOpt.PLAYER | GEUtil.TraceOpt.WORLD | GEUtil.TraceOpt.WEAPON,user)
    
    def IsInPlay( self, player ):
        return player.GetTeamNumber() is not GEGlobal.TEAM_SPECTATOR and self.pltracker.GetValue( player, self.trSpawned ) and not self.pltracker.GetValue( player, self.trEliminated )
    
    def getSidesColour(self,side):
        if side == GEGlobal.TEAM_MI6: return self.mColour
        else: return self.jColour

    def getSidesRadarColour(self,side,isREIcon=True):
        if side == GEGlobal.TEAM_MI6: 
            if isREIcon: return DieAnotherDay.mRERadarColour
            else: return DieAnotherDay.mUsedRERadarColour
        else:
            if isREIcon: return DieAnotherDay.jRERadarColour
            else: return DieAnotherDay.jUsedRERadarColour

    def getSidesResQueue(self,team):
        if team == GEGlobal.TEAM_MI6: return self.mResurrectionQueue
        else: return self.jResurrectionQueue         

    def updateResQueuePlayerCount(self,team):
        resQueue = self.getSidesResQueue(team)
        
        for player in resQueue:
            GEUtil.UpdateHudProgressBar(player,
                                        DieAnotherDay.resQueueMessageChannel,
                                        title="#GES_GP_DAD_RESURRECTION_QUEUE_POSITION\r" + str(resQueue.index(player) + 1))

    def drawEliminatedPlayerResQueueMessage(self,player,resQueue=None):
        if self.playerNotBot(player):
            if resQueue == None: 
                resQueue = self.getSidesResQueue(player.GetTeamNumber())
            
            GEUtil.InitHudProgressBar(player,
                                      DieAnotherDay.resQueueMessageChannel,
                                      title="#GES_GP_DAD_RESURRECTION_QUEUE_POSITION\r" + str(resQueue.index(player) + 1),
                                      flags=GEGlobal.HUDPB_TITLEONLY,
                                      x=-1, y=0.75,
                                      color=DieAnotherDay.RQPositionColour) 

    @staticmethod
    def playerNotBot(player):
        return player.__class__.__name__ != "CGEBotPlayer"

    def addPlayerToResurrectionQueue(self,player,team):
        teamsRQueue = None
        if team == GEGlobal.TEAM_MI6: teamsRQueue = self.mResurrectionQueue
        else: teamsRQueue = self.jResurrectionQueue
        #Player Insertion:
        if self.playerNotBot(player):
            positionOfBotNearestRQueueFront = self.getPositionOfBotNearestQueueFront(teamsRQueue)
            if positionOfBotNearestRQueueFront == -1: teamsRQueue.append(player)
            else:
                bot = teamsRQueue[positionOfBotNearestRQueueFront]
                teamsRQueue.insert(positionOfBotNearestRQueueFront,player)
                teamsRQueue.remove(bot) #TODO joe is this statement required?
                teamsRQueue.append(bot)
        #Bot Insertion:
        else: teamsRQueue.append(player)

    def getPositionOfBotNearestQueueFront(self,rQueue):
        for player in rQueue: 
            if self.playerNotBot(player) == False: return rQueue.index(player)
        return -1

    def removePlayerFromTeamsRQueue(self,player,team):
        rQueue = None
        if team == GEGlobal.TEAM_MI6: rQueue = self.mResurrectionQueue
        else: rQueue = self.jResurrectionQueue
        
        if player in rQueue:
            rQueue.remove(player)
            self.updateResQueuePlayerCount(team)

    def delayedResurrectionPBRemovalIfNoActiveResurrectionsAfterDelay(self,timer,update_type,player):
        if update_type == Timer.UPDATE_FINISH and not GEMPGameRules.IsIntermission():
            if self.resurrections.getPlayersResurrectionCount(player) == 0:
                GEUtil.RemoveHudProgressBar(player,DieAnotherDay.resurrectionPBIndex)

    def beginREInteraction(self,player,REArea,proximityInteraction):
        resurrection = self.resurrections.getREResurrection(player,REArea.GetGroupName())
        RE = self.REs.getRE(REArea.GetGroupName())
        if resurrection == None: self.resurrections.startNewResurrection(RE,player,proximityInteraction)
        else:
            if proximityInteraction: resurrection.proximityEnabled = True
            else: resurrection.LRREnabled = True

    def resurrectPlayerFromTeamIfTeamHasEliminatedPlayers(self,resurrector):
        areasTeam = resurrector.GetTeamNumber()

        #Choose player to be resurrected
        resurrectedPlayer = None
        if areasTeam == GEGlobal.TEAM_MI6 and len(self.mResurrectionQueue) != 0: resurrectedPlayer = self.mResurrectionQueue.pop(0)
        elif areasTeam == GEGlobal.TEAM_JANUS and len(self.jResurrectionQueue) != 0: resurrectedPlayer = self.jResurrectionQueue.pop(0)

        if resurrectedPlayer != None:
            self.pltracker.SetValue(resurrectedPlayer,self.trEliminated,False)
            self.eliminatedPlayerCount -= 1
            self.updateResQueuePlayerCount(areasTeam)
            return resurrectedPlayer
        return None

    def decideWhereREWillBeLocated(self,victim,killer,weapon):
        whenSpawnedMoveRETo = None
        
        if killer != None and weapon != None:
            if self.isPlayerTouchingGround(victim):
                whenSpawnedMoveRETo = victim.GetAbsOrigin()
            elif self.isPlayerJumping(victim):
                whenSpawnedMoveRETo = victim.GetAbsOrigin()
                #whenSpawnedMoveRETo = self.getVecForGroundBeneathJumpingPlayer(victim)#TODO Joe
            elif self.performStaircaseGapCheck(victim):
                whenSpawnedMoveRETo = victim.GetAbsOrigin()

        return whenSpawnedMoveRETo
    
    def isPlayerTouchingGround(self,player):
        return self.canFindGroundBeneathPlayer(player,self.maxDistanceBetweenGroundAndPlayerOrigin)

    def isPlayerJumping(self,player):
        if self.isPlayerTouchingGround(player):
            return False
        return self.canFindGroundBeneathPlayer(player,self.maxDistanceBetweenGroundAndJumpingPlayer)

    '''
    If canFindGroundBeneathPlayer() can't find ground directly beneath a player then they
    might be standing over a gap between two staircase steps. So this function searches for one of
    these steps.
    '''
    def performStaircaseGapCheck(self,player):
        def stepSearch(originVector):
            return GEUtil.Trace(originVector,
                                GEUtil.VectorMA(originVector,GEUtil.Vector(0,0,-1),self.maxDistanceBetweenGroundAndJumpingPlayer),
                                GEUtil.TraceOpt.WORLD | GEUtil.TraceOpt.PLAYER,player)

        originV = player.GetAbsOrigin()
        x = originV.__getitem__(0)
        y = originV.__getitem__(1)
        z = originV.__getitem__(2)

        returned = stepSearch(GEUtil.Vector(x,y - 3,z))
        if returned == None: returned = stepSearch(GEUtil.Vector(x + 3,y,z))
        if returned == None: returned = stepSearch(GEUtil.Vector(x,y + 3,z))
        if returned == None: returned = stepSearch(GEUtil.Vector(x - 3,y,z))
        return returned != None

    def canFindGroundBeneathPlayer(self,player,searchDistance):
        originV = player.GetAbsOrigin()
        endV = GEUtil.VectorMA(originV,GEUtil.Vector(0,0,-1),searchDistance)
        return GEUtil.Trace(originV,endV,GEUtil.TraceOpt.WORLD | GEUtil.TraceOpt.PLAYER,player) != None

    def isEliminatedPlayer(self,player):
        return self.pltracker.GetValue(player,self.trEliminated)

    #------------------------------
    
    '''Displays this HUD message: MI6:survivorCount/playerCount Janus:survivorCount/playerCount'''
    class HUDSurvivorCounts:
        ONTHINK_REFRESH_DELAY = 15 #= number of calls to be ignored, this delay is meant to be used in OnThink()
        mSCountPBIndex = 0
        jSCountPBIndex = 1

        def __init__(self, x=0.30, y=0.01):
            self.x = x
            self.y = y
            self.refreshDelay = self.ONTHINK_REFRESH_DELAY
            self.mPlayerCount = 0
            self.mSurvivorCount = 0
            self.jPlayerCount = 0
            self.jSurvivorCount = 0
            self.displayed = False

        ''''Exists because GetNumActiveTeamPlayers2() doesn't count players in observer mode who have stopped being spectators

        TODO Delete when fixed and update calls.
        '''
        def GetNumActiveTeamPlayers2(self, team):
            players = []
            for i in range(32):
                if GEPlayer.IsValidPlayerIndex(i):
                    player = GEPlayer.GetMPPlayer(i)
                    if player.GetTeamNumber() == team:
                        players.append(player)

            return len(players)
            
        def show(self):
            self.refresh()
            self.draw()
            self.displayed = True

        def hide(self):
            GEUtil.RemoveHudProgressBar(None,self.mSCountPBIndex)
            GEUtil.RemoveHudProgressBar(None,self.jSCountPBIndex)
            self.displayed = False

        '''
        This will update the displayed information if this information needs to be updated.
        '''
        def refresh(self,useOnThinkDelay=False):
            if useOnThinkDelay:
                if self.refreshDelay != 0:
                    self.refreshDelay -= 1
                    return
                else:
                    self.refreshDelay = self.ONTHINK_REFRESH_DELAY

            #Get the latest team info:
            currentMPlayerCount = self.GetNumActiveTeamPlayers2(GEGlobal.TEAM_MI6) #TODO replace when fixed
            currentJPlayerCount = self.GetNumActiveTeamPlayers2(GEGlobal.TEAM_JANUS) #TODO replace when fixed
            currentMSurvivorCount = GEMPGameRules.GetNumInRoundTeamPlayers(GEGlobal.TEAM_MI6)
            currentJSurvivorCount = GEMPGameRules.GetNumInRoundTeamPlayers(GEGlobal.TEAM_JANUS)

            #Update stored info:
            mPCountNeedsUpdate = False
            jPCountNeedsUpdate = False
            mSCountNeedsUpdate = False
            jSCountNeedsUpdate = False
            if self.mPlayerCount != currentMPlayerCount:
                self.mPlayerCount = currentMPlayerCount
                mPCountNeedsUpdate = True
            if self.jPlayerCount != currentJPlayerCount:
                self.jPlayerCount = currentJPlayerCount
                jPCountNeedsUpdate = True
            if self.mSurvivorCount != currentMSurvivorCount:
                self.mSurvivorCount = currentMSurvivorCount
                mSCountNeedsUpdate = True
            if self.jSurvivorCount != currentJSurvivorCount:
                self.jSurvivorCount = currentJSurvivorCount
                jSCountNeedsUpdate = True

            #Update displayed info:
            if self.displayed:
                if mPCountNeedsUpdate: self.draw(GEGlobal.TEAM_MI6)
                elif mSCountNeedsUpdate: self.updateDisplayedSurvivorCount(GEGlobal.TEAM_MI6)
                if jPCountNeedsUpdate: self.draw(GEGlobal.TEAM_JANUS)
                elif jSCountNeedsUpdate: self.updateDisplayedSurvivorCount(GEGlobal.TEAM_JANUS)

        def updateDisplayedSurvivorCount(self, team=None):
            if team == None or GEGlobal.TEAM_MI6:
                GEUtil.UpdateHudProgressBar(None, self.mSCountPBIndex, self.mSurvivorCount)
            if team == None or GEGlobal.TEAM_JANUS:
                GEUtil.UpdateHudProgressBar(None, self.jSCountPBIndex, self.jSurvivorCount)

        def draw(self, team=None):
            if team == None or GEGlobal.TEAM_MI6:
                GEUtil.InitHudProgressBar(None,
                                          self.mSCountPBIndex,
                                          "MI6:",
                                          GEGlobal.HUDPB_SHOWVALUE,
                                          self.mPlayerCount,
                                          self.x,
                                          self.y,
                                          120,
                                          60,
                                          GEUtil.CColor(0,150,255,255),
                                          self.mSurvivorCount)
            if team == None or GEGlobal.TEAM_JANUS:
                GEUtil.InitHudProgressBar(None,
                                          self.jSCountPBIndex,
                                          "Janus:",
                                          GEGlobal.HUDPB_SHOWVALUE,
                                          self.jPlayerCount,
                                          self.x + 0.20,
                                          self.y,
                                          120,
                                          60,
                                          GEUtil.Color(255,0,0,255),
                                          self.jSurvivorCount)

    '''
        This class is responsible for detecting when a player has stopped aiming a LRR beam at a RE they are using.
        
        The resurrection class uses self.targetMissed to find out when a monitor has detected this and it will then stop the target monitor.
        
        @Client class: Resurrection
    '''    
    class LRRTargetMonitor:
        drawnLaserDuration = 0.4
        aimCheckRate = 0.2
        
        def __init__(self,resurrectionP):
            self.targetMissed = False
            self.DAD = resurrectionP.DAD
            self.resurrection = resurrectionP
            self.secsSinceLaserDrawn = 0
            
            self.targetCheckTimer = None            
            self.targetCheckTimer = self.DAD.timerTracker.CreateTimer("LRRTargetMonitor:" + self.resurrection.user.GetPlayerName())
            self.targetCheckTimer.SetAgeRate(1.0,0)
            self.targetCheckTimer.SetUpdateCallback(self.monitorPlayersLRRTarget,self.aimCheckRate)
            
            self.laserColour = self.DAD.getSidesColour(self.resurrection.user.GetTeamNumber())
            self.DAD.playersLRRTargetMonitor[self.resurrection.user] = self
            self.REContactVector = GEUtil.VectorMA(self.resurrection.RE.location,GEUtil.Vector(0,0,1),40)
        
        def start(self):
            self.targetCheckTimer.Start()
            
        def stop(self):
            self.targetCheckTimer.Stop()
        
        def delete(self):
            self.targetCheckTimer.Stop()
            self.DAD.timerTracker.RemoveTimer(self.targetCheckTimer.GetName())
            del self.DAD.playersLRRTargetMonitor[self.resurrection.user]
        
        def monitorPlayersLRRTarget(self,timer,update_type):
            #1.Draw the first temporary beam to the RE
            if not GEMPGameRules.IsIntermission():
                if update_type == Timer.UPDATE_START:
                    self.drawLaser()
                elif update_type == Timer.UPDATE_RUN:
                    #2. [Player's LRR beam is still hitting the friendly RE]
                    if self.resurrection.RE.isEntity(DieAnotherDay.getEntHitByLRRLaser(self.resurrection.user)):
                        #3. Draw a new temporary beam to the RE
                        self.drawLaser()
                    #Exception: Record that this monitor's target has been missed before its associated resurrection ended.
                    else:
                        self.DAD.resurrections.playerHasCeasedTargettingRE(self.resurrection)
            
        def drawLaser(self):
            GEUtil.CreateTempEnt(GEUtil.TempEnt.BEAM,origin=self.resurrection.user.GetEyePosition(),end=self.REContactVector,duration=self.drawnLaserDuration + 0.2,color=self.laserColour)                             

    class ExtCallbackTimer:
            instanceID = 0
            def __init__(self,timerTrackerP,extCallbackP,runParameterP,callbackRate=1.0,ageRate=1.0):
                self.extCallback = extCallbackP
                self.runParameter = runParameterP
                
                self.timerTracker = timerTrackerP
                instanceIDBefore = DieAnotherDay.ExtCallbackTimer.instanceID
                DieAnotherDay.ExtCallbackTimer.instanceID = instanceIDBefore + 1
                self.timer = self.timerTracker.CreateTimer("CallbackTimer:" + str(instanceIDBefore))
                self.timer.SetUpdateCallback(self.TimerTick,callbackRate)
                self.timer.SetAgeRate(ageRate)
                
            def TimerTick(self,timer,update_type):
                self.extCallback(timer,update_type,self.runParameter)
                if update_type == Timer.UPDATE_FINISH: self.timerTracker.RemoveTimer(self.timer.GetName())
                
            def start(self,duration):
                self.timer.Start(duration)
                
            def stop(self):
                self.timer.Stop()

    class REDict:
        def __init__(self,DADP):
            self.unusedAreaID = 0
            self.DAD = DADP
            self.REs = {}
            
        def cleanup(self):
            self.DAD = None
            for RE in self.REs.values(): RE.cleanup()
            self.REs = None
            
        def getRE(self,ID):
            return self.REs[ID]
            
        def flagREAsUsed(self,ID):
            self.REs[ID].used = True
            
        def hasREBeenUsed(self,ID):
            return self.REs[ID].used
            
        def getListOfTeamsREs(self,teamP):
            teamsREs = []
            for RE in self.REs.values():
                if RE.team == teamP: teamsREs.append(RE)
                
            return teamsREs
        
        def areaSpawned(self,area):
            self.REs[area.GetGroupName()].areaSpawned(area)
            
        def spawnNewResurrectionEntity(self,victim,team,afterSpawnMoveTo=None):
            newAreasID = str(self.unusedAreaID)
            self.unusedAreaID += 1
            self.spawnResurrectionEntity(newAreasID,team,afterSpawnMoveTo)
        
        def spawnResurrectionEntity(self,areaID,team,afterSpawnMoveTo=None):
            skinNumber = 1
            if team == GEGlobal.TEAM_MI6: skinNumber = 0
            
            self.DAD.tokenManager.SetupCaptureArea(areaID, 
                                                   radius = 35,
                                                   model="models/gameplay/gravestone.mdl",
                                                   limit=1,
                                                   #glow_color=self.DAD.getSidesColour(team),
                                                   #glow_dist=0,
                                                   skin=skinNumber,
                                                   rqd_team=team)
            
            self.REs[areaID] = DieAnotherDay.REDict.RE(self.DAD,areaID,team)
            
            if afterSpawnMoveTo != None: self.REs[areaID].setMoveToLocation(afterSpawnMoveTo)
            
        def makeREGlow(self,RE):
            self.DAD.tokenManager.SetupCaptureArea(RE.GetGroupName(),glow_dist=350)
            
        def disableREGlow(self,RE):
            self.DAD.tokenManager.SetupCaptureArea(RE.GetGroupName(),glow_dist=0)
#         
        def areaUsable(self,area):
            ID = area.GetGroupName()
            if ID in self.REs.keys():
                RE = self.REs[ID]
                return RE.disabled == False and RE.used == False
                
            return False
            
        def deleteRE(self,ID):
            del self.REs[ID]
            self.DAD.tokenManager.RemoveCaptureArea(ID)
            
        def doesREExsist(self,ID):
            return ID in self.REs.keys()
            
        def deleteREAfterDelay(self,ID,delay):
            timer = DieAnotherDay.ExtCallbackTimer(self.DAD.timerTracker,self.deleteREAfterDelayCallback,ID)
            timer.start(delay)
            
        def deleteREAfterDelayCallback(self,timer,update_type,ID):
            if update_type == Timer.UPDATE_FINISH and not GEMPGameRules.IsIntermission():
                self.deleteRE(ID)
            
        def deleteAll(self):
            for RE in self.REs.values(): RE.delete()
            self.REs = {}
            self.unusedAreaID = 0
            
        def getTeamsRELocations(self,teamP):
            foundLocations = []
            for RE in self.REs.values():
                if RE.team == teamP: foundLocations.append(RE.getLocation())
            return foundLocations
            
        def needsToBeMoved(self,ID):
            return self.REs[ID].needsToBeMoved()
        
        def moveToDeathLocation(self,ID):
            self.REs[ID].move()
            
        def isPulsating(self,ID):
            return self.REs[ID].isPulsating()
             
        def startPulsatingRings(self,ID):
            self.REs[ID].pulsate()
         
        def stopPulsatingRings(self,ID):
            self.REs[ID].stopPulsating()
            
        class RE:
            creationOrderNumber = 0
            
            def __init__(self,DADP,IDP,teamP):
                self.disabled = True
                self.DAD = DADP
                
                self.ID = IDP
                self.team = teamP
                self.areasHandle = None
                self.pulseTimer = None
                self.needsToBeMovedTo = None
                self.used = False
                self.location = None
                self.userCount = 0
                
            def cleanup(self):
                self.areasHandle = None
                self.pulseTimer = None
                self.needsToBeMovedTo = None
                self.location = None
                
            def delete(self):
                if self.pulseTimer != None: self.pulseTimer.stop()
                self.DAD.tokenManager.RemoveCaptureArea(self.ID)
                self.cleanup()
                
            def areaSpawned(self,area):
                self.areasHandle = GEEntity.EntityHandle(area)
                self.pulseTimer = DieAnotherDay.REDict.RE.RingPulseTimer(self.DAD,area)
                self.location = area.GetAbsOrigin()
                self.disabled = False
                
            def makeInvisible(self):
                self.DAD.tokenManager.SetupCaptureArea(self.ID,model="",glow_dist=0)
                
            def isEntity(self,entity):
                area = self.areasHandle.Get()
                if area == None:
                    GEUtil.DevWarning("RE.isEntity() failed: area handle returned None.\n")
                    return None
                
                return area == entity
                
            def clearObjective(self):
                area = self.areasHandle.Get()
                if area == None:
                    GEUtil.DevWarning("RE.clearObjective() failed: area handle returned None.\n")
                    return None
                
                self.DAD.radar.ClearObjective(area)
                
            def setupObjective(self,team):
                area = self.areasHandle.Get()
                if area == None:
                    GEUtil.DevWarning("RE.setupObjective() failed: area handle returned None.\n")
                    return None
                
                if team == None: team = area.GetTeamNumber()
                self.DAD.radar.SetupObjective(area,team,"","",self.DAD.getSidesColour(team),200,True)
                
            def setupYellowObjective(self):
                area = self.areasHandle.Get()
                if area == None:
                    GEUtil.DevWarning("RE.setupYellowObjective() failed: area handle returned None.\n")
                    return None
                
                self.DAD.radar.SetupObjective(area,area.GetTeamNumber(),"","",DieAnotherDay.RQPositionColour,200,True)
                
            def setMoveToLocation(self,location):
                self.needsToBeMovedTo = location
                
            def needsToBeMoved(self):
                return self.needsToBeMovedTo != None
            
            def move(self):
                if self.needsToBeMovedTo == None:
                    GEUtil.DevWarning("RE.move() failed: needsToBeMovedTo = None\n")
                    return False
                
                area = self.areasHandle.Get()
                if area == None:
                    GEUtil.DevWarning("RE.move() failed: area handle returned None.\n")
                    return False
                
                area.SetAbsOrigin(self.needsToBeMovedTo)
                self.location = self.needsToBeMovedTo
                self.pulseTimer.origin = self.location
                self.needsToBeMovedTo = None
                
            def changeRadarIconAfterDelay(self,icon,colour,delay):
                timer = DieAnotherDay.ExtCallbackTimer(self.DAD.timerTracker,self.changRadarIconAfterDelayCB,{"icon":icon,"colour":colour})
                timer.start(delay)
            
            def changRadarIconAfterDelayCB(self,timer,update_type,parameters):
                if update_type == Timer.UPDATE_FINISH and not GEMPGameRules.IsIntermission():
                    self.changeRadarIcon(parameters["icon"],parameters["colour"])
                
            def changeRadarIcon(self,newIcon,colour):
                area = self.areasHandle.Get()
                if area == None:
                    GEUtil.DevWarning("RE.changeRadarIcon() failed: area handle returned None.\n")
                    return False
                
                self.DAD.radar.DropRadarContact(area)
                self.DAD.radar.AddRadarContact(area,GEGlobal.RADAR_TYPE_OBJECTIVE,True,newIcon,colour)
                
            def pulsate(self):
                self.pulseTimer.start()
                
            def stopPulsating(self):
                self.pulseTimer.stop()
                
            def isPulsating(self):
                return self.pulseTimer.isPulsating()
            
            ''''
            This class is responsible for drawing pulsating rings around active REs
            '''
            class RingPulseTimer:
                def __init__(self,DADP,area):
                    self.DAD = DADP
                    self.timer = self.DAD.timerTracker.CreateTimer("RingPulseTimer:" + area.GetGroupName())
                    self.timer.SetUpdateCallback(self.TimerTick,0.5)
                    self.timer.SetAgeRate(1.0,0) 
                    self.PULSE_COLOUR = self.DAD.getSidesColour(area.GetTeamNumber())
                    self.origin = area.GetAbsOrigin()
                    
                def start(self):
                    self.timer.Start()
                    
                def stop(self):
                    self.timer.Stop()
                    
                def isPulsating(self):
                    return self.timer.state != Timer.STATE_STOP
                    
                def TimerTick( self, timer, update_type ):
                    if not GEMPGameRules.IsIntermission() and update_type != Timer.UPDATE_STOP and update_type == Timer.UPDATE_RUN:
                        self.DrawNewRing()
                
                def DrawNewRing( self ):
                    GEUtil.CreateTempEnt(GEUtil.TempEnt.RING,origin=self.origin,framerate=15,duration=2,speed=10,width=0.33,amplitude=0.0,radius_start=0,radius_end=220,color=self.PULSE_COLOUR)
           
                def delete(self):
                    self.DAD.timerTracker.RemoveTimer(self.timer.GetName())

    class ResurrectionDict:
        def __init__(self,DADP):
            self.DAD = DADP
            self.resurrections = {}
            
        def cleanup(self):
            self.DAD = None
            self.resurrections = None
            
        def isResurrectionKnown(self,resurrectionP):
            return self.resurrections.has_key(resurrectionP.getID())
        
        def startNewResurrection(self,RE,user,startedAtCloseRange):
            newResurrection = DieAnotherDay.Resurrection(self.DAD,RE,user,startedAtCloseRange)
            idP = newResurrection.getID()
            self.resurrections[idP] = newResurrection
            self.resurrections[idP].start()
            return newResurrection
        
        def deleteNotInUseRE(self,team):
            #Find not in use REs:
            teamsREs = self.DAD.REs.getListOfTeamsREs(team)
            for resurrection in self.resurrections.values():
                if resurrection.RE in teamsREs: teamsREs.remove(resurrection.RE)
                
            #Delete a not in use RE:
            if len(teamsREs) != 0: 
                self.DAD.REs.deleteRE(teamsREs.pop().ID)
                return True
            else: return False
            
        def delete(self,resurrection):
            del self.resurrections[resurrection.getID()]
                
        def getREsResurrections(self,REP):
            found = []
            
            for resurrection in self.resurrections.values():
                if resurrection.RE == REP: 
                    found.append(resurrection)
            return found
            
        def getPlayersResurrectionCount(self,player):
            return len(self.getPlayersResurrections(player))
        
        def cancelREResurrections(self,IDP,ignoreID=-1):
            for resurrection in self.resurrections.values():
                if resurrection.RE.ID == IDP and resurrection.ID != ignoreID: resurrection.stop()
                
        def cancelResurrections(self):
            for resurrection in self.resurrections.values(): resurrection.resurrectionFailed()
        
        def getREResurrection(self,player,REID):
            for resurrection in self.resurrections.values():
                if resurrection.user == player and resurrection.RE.ID == REID: return resurrection
            
            return None
        
        def getPlayersResurrections(self,player):
            playersResurrections = []
            
            for resurrection in self.resurrections.values():
                if resurrection.user == player: playersResurrections.append(resurrection)
                
            return playersResurrections
        
        def getPlayersMostRecentResurrection(self,player):
            playersResurrections = self.getPlayersResurrections(player)
            highestIDNumber = playersResurrections[0].ID
            resWithHighestID = playersResurrections[0]
            
            for resurrection in playersResurrections:
                if highestIDNumber < resurrection.ID:
                    highestIDNumber = resurrection.ID
                    resWithHighestID = resurrection
                
            return resWithHighestID
        
        def isPlayersMostRecentResurrection(self,player,resurrection):
            return self.getPlayersMostRecentResurrection(player) == resurrection
        
        def playerHasDisconnected(self,player):
            for resurrection in self.getPlayersResurrections(player): resurrection.hasUserDisconnected = True
            
        def playerHasBeenKilled(self,player):
            for resurrection in self.getPlayersResurrections(player): resurrection.hasUserDied = True
            
        def playerHasExitedFriendlyREArea(self,area,player):
            resurrection = self.getREResurrection(player,area.GetGroupName())
            if resurrection != None: resurrection.proximityEnabled = False
            
        def playerHasCeasedTargettingRE(self,resurrectionP):
            for resurrection in self.resurrections.values():
                if resurrection.ID == resurrectionP.ID: resurrection.LRREnabled = False

    ''''
    This class is responsible for handling succesful and interrupted resurrections.
    '''
    class Resurrection:
        USED_RE_ICON = ""
        unusedID = 0
        
        def __init__(self,DADP,REP,userP,startedAtCloseRange):
            self.ID = DieAnotherDay.Resurrection.unusedID
            DieAnotherDay.Resurrection.unusedID += 1
            
            self.timer = None
            self.DAD = DADP
            self.RE = REP
            self.user = userP
            self.team = self.user.GetTeamNumber()
            self.timer = self.DAD.timerTracker.CreateTimer("ResurrectionTimer:" + self.getID())
            self.timer.SetUpdateCallback(self.ResurrectionHandler,1.0)
            self.timer.SetAgeRate(1.0,0)
            self.LRRMonitorExists = False
            
            #Resurrection Interrupt Flags
            self.hasUserDisconnected = False
            self.hasUserDied = False
            self.LRREnabled = False
            self.proximityEnabled = False
            
            if startedAtCloseRange:  self.proximityEnabled = True
            else: self.LRREnabled = True
            
        def getID(self):
            return self.RE.ID + ":" + self.user.GetPlayerName()
        
        def start(self):
            if self.timer.state == Timer.STATE_STOP : self.timer.Start(self.DAD.resurrectionTime,False)
            else: GEUtil.DevWarning("Start() has been called for a resurrection which is already running, so it was ignored:" + self.getID() + "\n")
            return False
            
        def getRemainingTime(self):
            return self.DAD.resurrectionTime - self.timer.GetCurrentTime()
        
        def stop(self):
            self.resurrectionFailed()
        
        def resurrectionFailed(self):
            self.timer.Stop()
            self.RE.userCount -= 1
            
            #Delete the resurrection timer.
            self.DAD.timerTracker.RemoveTimer(self.timer.GetName())
            #Stop LRR Target Monitor
            if self.DAD.playersLRRTargetMonitor.has_key(self.user): 
                self.DAD.playersLRRTargetMonitor[self.user].delete()
                self.LRRMonitorExists = False
            
            #If nesscary, change the appearance of the RE to show its not being used:
            if self.DAD.REs.doesREExsist(self.RE.ID) and self.RE.used == False:
                if self.RE.userCount == 0: 
                    #Stop pulsating RE Rings
                    self.DAD.REs.stopPulsatingRings(self.RE.ID)
                    #Stop glow
                    #self.DAD.REs.disableREGlow(self.RE)
                    
                    #Make the objective icon become its normal colour
                    self.RE.clearObjective()
                    self.RE.setupObjective(self.team)
            
            #Delete this resurrection object
            self.DAD.resurrections.delete(self)
            
            #Remove Resurrection Progress Bar
            if self.hasUserDisconnected == False:
                usersResCount = self.DAD.resurrections.getPlayersResurrectionCount(self.user)
                if usersResCount == 0:
                    GEUtil.RemoveHudProgressBar(self.user,DieAnotherDay.resurrectionPBIndex)
                else:
                    #The resurrection count will need to be updated:
                    GEUtil.UpdateHudProgressBar(self.user,self.DAD.resurrectionPBIndex,0,str(usersResCount),self.DAD.getSidesColour(self.team))
        
        #Everything that happens in successful and interrupted resurrections is implemented/called in this timer function:
        def ResurrectionHandler( self, timer, update_type ):
            #Resurrection failure response:
            if update_type != Timer.UPDATE_STOP and not GEMPGameRules.IsIntermission():
                if self.RE.disabled or self.RE.used:
                    self.timer.Stop()
                else:
                    if update_type == Timer.UPDATE_START:
                        #1. Start a LRR target monitor:
                        if self.LRREnabled:
                            LRRTargetMonitor = DieAnotherDay.LRRTargetMonitor(self)
                            LRRTargetMonitor.start()
                            self.LRRMonitorExists = True
                        
                        self.RE.userCount += 1
                        if self.RE.userCount == 1:
                            #2. If this RE isn't already pulsating because of another resurrection:
                            self.DAD.REs.startPulsatingRings(self.RE.ID)
                            #Make the RE glow
                            #self.DAD.REs.makeREGlow(self.RE)
                            #3. Make the RE's objective icon become yellow, if it doesn't already look like this:
                            self.RE.clearObjective()
                            self.RE.setupYellowObjective()
                        #4. [Resurrection bar not already shown] Show the resurrection progress bar:
                        usersResCount = self.DAD.resurrections.getPlayersResurrectionCount(self.user)
                        if usersResCount == 1: GEUtil.InitHudProgressBar(self.user,self.DAD.resurrectionPBIndex,"1",GEGlobal.HUDPB_SHOWBAR,self.DAD.resurrectionTime,-1,DieAnotherDay.resBarY,120,16,self.DAD.getSidesColour(self.team))
                        else: GEUtil.UpdateHudProgressBar(self.user,self.DAD.resurrectionPBIndex,0,str(usersResCount),self.DAD.getSidesColour(self.team))
                    
                    elif update_type == Timer.UPDATE_RUN:
                        #If the resurrection has failed:
                        if self.hasUserDisconnected or self.hasUserDied or self.team != self.user.GetTeamNumber(): self.resurrectionFailed()
                        elif self.LRREnabled == False and self.proximityEnabled == False: 
                            self.resurrectionFailed() #TESTED
                        #If it hasn't failed:
                        else:
                            #Enable/Disable a LRR target monitor if nesscary:
                            if self.LRREnabled and self.LRRMonitorExists == False:
                                #Start a LRR target monitor:
                                LRRTargetMonitor = DieAnotherDay.LRRTargetMonitor(self)
                                LRRTargetMonitor.start()
                                self.LRRMonitorExists = True
                            elif self.LRREnabled == False and self.LRRMonitorExists:
                                #Stop LRR Target Monitor
                                self.DAD.playersLRRTargetMonitor[self.user].delete()
                                self.LRRMonitorExists = False
                            
                            if self.DAD.resurrections.isPlayersMostRecentResurrection(self.user,self):
                                    #5. Update the resurrection progress bar:
                                    GEUtil.UpdateHudProgressBar(self.user,DieAnotherDay.resurrectionPBIndex,int(self.timer.GetCurrentTime()),str(self.DAD.resurrections.getPlayersResurrectionCount(self.user)))
                    #End a succesful resurrection:
                    elif update_type == Timer.UPDATE_FINISH: 
                        #6. Cancel the other resurrections for this resurrection's RE and prevent new resurrections from starting for it, before it's deleted.
                        self.DAD.REs.flagREAsUsed(self.RE.ID)
                        self.DAD.resurrections.cancelREResurrections(self.RE.ID,self.ID)
                        #7.Stop target monitor
                        if self.LRRMonitorExists: self.DAD.playersLRRTargetMonitor[self.user].delete()
                        #8.Disable the RE and make it Invisible
                        self.RE.clearObjective()
                        self.RE.makeInvisible()
                        #9.Give the invisible RE an objective icon for the enemy team, to show them where a player was resurrected.
                        enemyTeam = GEGlobal.TEAM_MI6
                        if self.team == GEGlobal.TEAM_MI6: enemyTeam = GEGlobal.TEAM_JANUS
                        self.RE.clearObjective()
                        self.RE.setupObjective(enemyTeam)
                        #10. Delete the resurrection timer
                        self.DAD.timerTracker.RemoveTimer(self.timer.GetName())
                        #11.Stop pulsating RE Rings
                        self.RE.stopPulsating()
                        #12.Change the RE's radar icon into the yellow Used RE icon:
                        self.RE.changeRadarIcon("sprites/hud/radar/run",self.DAD.RQPositionColour)
                        #13.If the user has no other resurrections:
                        if self.DAD.resurrections.getPlayersResurrectionCount(self.user) == 1:
                            #14.Make the progress bar yellow for a moment and change the progress bar's resurrection count to 0:
                            GEUtil.UpdateHudProgressBar(self.user,self.DAD.resurrectionPBIndex,self.DAD.resurrectionTime,"0",DieAnotherDay.RQPositionColour)
                            #15.Remove the resurrection progress bar.
                            progressBarRemovalTimer = DieAnotherDay.ExtCallbackTimer(self.DAD.timerTracker,self.DAD.delayedResurrectionPBRemovalIfNoActiveResurrectionsAfterDelay,self.user)
                            progressBarRemovalTimer.start(3)
                        #16.Resurrect a player from the user's team
                        resurrectedPlayer = self.DAD.resurrectPlayerFromTeamIfTeamHasEliminatedPlayers(self.user)
                        if(resurrectedPlayer != None):
                            self.DAD.resurrectedPlayers.append(resurrectedPlayer)
                            #17.Increment the RE user's score:
                            self.user.AddRoundScore( 1 )
                            #18.Remove the resurrection queue position message from the resurrected player's screen.
                            GEUtil.RemoveHudProgressBar(resurrectedPlayer, DieAnotherDay.resQueueMessageChannel)
                            #19.Announce the resurrection.
                            playersName = resurrectedPlayer.GetPlayerName()
                            GEUtil.EmitGameplayEvent("DAD_Resurrection","%s" % playersName,"%i" % self.team,"%s" % self.user.GetPlayerName())
                            if self.team == GEGlobal.TEAM_MI6: GEUtil.ClientPrint(None,GEGlobal.HUD_PRINTTALK,"#GES_GP_DAD_MI6_PLAYER_RESURRECTED",playersName)
                            else:GEUtil.ClientPrint(None,GEGlobal.HUD_PRINTTALK,"#GES_GP_DAD_JANUS_PLAYER_RESURRECTED",playersName)
                            #20.After a few seconds of being yellow, change the "used RE" icons colour to be the used RE's side's colour.
                            self.RE.changeRadarIconAfterDelay("sprites/hud/radar/run",self.DAD.getSidesRadarColour(self.team,False),3.0)
                            #21.After the "used RE" radar icon has not been yellow for X seconds, remove it and delete the RE.
                            self.DAD.REs.deleteREAfterDelay(self.RE.ID,self.DAD.usedRELocationRevealTime)
                        else: self.DAD.REs.deleteRE(self.RE.ID)
                        #22. Delete this resurrection object
                        self.DAD.resurrections.delete(self)
