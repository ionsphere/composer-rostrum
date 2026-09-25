-- Protocol v1 worker. Run only inside the isolated Rostrum REAPER process.
local source = debug.getinfo(1,'S').source:sub(2)
local json = dofile(source:match('^(.*[/\\])') .. 'json.lua')
-- Windows can resolve a busy directory with the extended-length //?/ prefix.
-- REAPER's render dialog does not accept that spelling as a destination.
local workspace = assert(ROSTRUM_WORKSPACE, 'ROSTRUM_WORKSPACE is required'):gsub('^//%?/','')
local project_path = workspace..'/project.rpp'
local function copy(v) return json.decode(json.encode(v)) end
local function load(path) local f=assert(io.open(path,'rb')); local s=f:read('*a'); f:close(); return json.decode(s) end
local function write(path,v)
  local f=assert(io.open(path..'.tmp','wb')); f:write(json.encode(v)); f:close(); assert(os.rename(path..'.tmp',path))
end
local function setext(obj, key, value, track)
  if track then reaper.GetSetMediaTrackInfo_String(obj,'P_EXT:'..key,value,true)
  else reaper.GetSetMediaItemInfo_String(obj,'P_EXT:'..key,value,true) end
end
local function getext(obj,key,track)
  local _,s
  if track then _,s=reaper.GetSetMediaTrackInfo_String(obj,'P_EXT:'..key,'',false)
  else _,s=reaper.GetSetMediaItemInfo_String(obj,'P_EXT:'..key,'',false) end
  return s
end
local function rounded(v) return math.floor(v*1e9+0.5)/1e9 end
local function qn(t) return rounded(reaper.TimeMap2_timeToQN(0,t)) end
local function seconds(b) return reaper.TimeMap2_QNToTime(0,b) end
local handlers={}
handlers.ping=function() return {protocol=1,pong=true,bridge_version='1.0'} end
handlers.capabilities=function()
  return {protocol=1,bridge_version='1.0',reaper_version=reaper.GetAppVersion(),
    capabilities={midi_notes=true,audio_clips=true,sampler=false,native_synth=true,native_eq=false,
      compression=false,sidechain=false,automation=false,offline_render=true,readback=true,headless_or_unattended=true}}
end

-- Templates retain optional fields and non-native metadata. All supported musical
-- fields are read from REAPER, not copied back from the input to fake conformance.
handlers.materialize=function(a)
  local p=a.project
  local existing={}; local previous={tracks={}}
  local valid,template=reaper.GetProjExtState(0,'rostrum','template')
  if valid~=0 then previous=json.decode(template) end
  for i=0,reaper.CountTracks(0)-1 do
    local tr=reaper.GetTrack(0,i); existing[getext(tr,'rostrum_id',true)]=tr
  end
  for i=reaper.CountTempoTimeSigMarkers(0)-1,0,-1 do reaper.DeleteTempoTimeSigMarker(0,i) end
  local num,den=p.meter:match('^(%d+)/(%d+)$')
  reaper.SetTempoTimeSigMarker(0,-1,0,-1,-1,p.tempo,tonumber(num),tonumber(den),false)
  reaper.SetProjExtState(0,'rostrum','template',json.encode(p))
  for ti,t in ipairs(p.tracks) do
    local tr=existing[t.id]; local fresh=tr==nil
    if fresh then reaper.InsertTrackAtIndex(ti-1,false); tr=reaper.GetTrack(0,ti-1) end
    setext(tr,'rostrum_id',t.id,true)
    reaper.GetSetMediaTrackInfo_String(tr,'P_NAME',t.name or t.id,true)
    reaper.SetMediaTrackInfo_Value(tr,'B_MUTE',t.muted and 1 or 0)
    reaper.SetMediaTrackInfo_Value(tr,'D_VOL',10^((t.gain_db or 0)/20))
    reaper.SetMediaTrackInfo_Value(tr,'D_PAN',t.pan or 0)
    if t.kind=='midi' and fresh then
      assert(reaper.TrackFX_AddByName(tr,'Rostrum/rostrum_sine',false,1)>=0,'Rostrum instrument missing')
    end
    local fxstart=t.kind=='midi' and 1 or 0
    for fi,effect in ipairs(t.effects or {}) do
      local index=fxstart+fi-1
      if index>=reaper.TrackFX_GetCount(tr) then
        assert(reaper.TrackFX_AddByName(tr,'Rostrum/rostrum_gain',false,-1)>=0,'Rostrum gain effect missing')
      end
      reaper.TrackFX_SetParam(tr,index,0,effect.gain_db)
    end
    for _,c in ipairs(t.clips or {}) do
      local item,take
      local old
      for _,pt in ipairs(previous.tracks) do if pt.id==t.id then
        for _,pc in ipairs(pt.clips or {}) do if pc.id==c.id then old=pc end end
      end end
      for ci=0,reaper.CountTrackMediaItems(tr)-1 do
        local candidate=reaper.GetTrackMediaItem(tr,ci)
        if getext(candidate,'rostrum_id',false)==c.id then item=candidate; break end
      end
      if item and old and json.encode(old)==json.encode(c) and previous.tempo==p.tempo then goto next_clip end
      if c.kind=='midi' then
        item=item or assert(reaper.CreateNewMIDIItemInProj(tr,c.start,c.start+c.length,true))
        reaper.SetMediaItemInfo_Value(item,'D_POSITION',seconds(c.start))
        reaper.SetMediaItemInfo_Value(item,'D_LENGTH',seconds(c.start+c.length)-seconds(c.start))
        take=assert(reaper.GetActiveTake(item))
        local _,nn,nc,nt=reaper.MIDI_CountEvts(take)
        for i=nn-1,0,-1 do reaper.MIDI_DeleteNote(take,i) end
        for i=nc-1,0,-1 do reaper.MIDI_DeleteCC(take,i) end
        for i=nt-1,0,-1 do reaper.MIDI_DeleteTextSysexEvt(take,i) end
        for ni,n in ipairs(c.notes or {}) do
          local start=math.floor(reaper.MIDI_GetPPQPosFromProjQN(take,c.start+n.start)+0.5)
          local finish=math.floor(reaper.MIDI_GetPPQPosFromProjQN(take,c.start+n.start+n.duration)+0.5)
          assert(reaper.MIDI_InsertNote(take,false,false,start,finish,n.channel or 0,n.pitch,n.velocity,true))
          reaper.MIDI_InsertTextSysexEvt(take,false,false,start,1,'rostrum:'..json.encode({id=n.id,index=ni,pitch=n.pitch,channel=n.channel or 0}),true)
        end
        reaper.MIDI_Sort(take)
      else
        local asset
        for _,candidate in ipairs(p.assets) do if candidate.id==c.asset_id then asset=candidate end end
        assert(asset,'asset missing')
        if not item then
          item=reaper.AddMediaItemToTrack(tr); take=reaper.AddTakeToMediaItem(item)
          local src=assert(reaper.PCM_Source_CreateFromFile(asset.path),'cannot open audio fixture')
          reaper.SetMediaItemTake_Source(take,src)
        else take=assert(reaper.GetActiveTake(item)) end
        reaper.SetMediaItemInfo_Value(item,'D_POSITION',seconds(c.timeline_start_beats or 0))
        reaper.SetMediaItemInfo_Value(item,'D_LENGTH',(c.source_end-c.source_start)*(c.stretch_ratio or 1))
        reaper.SetMediaItemTakeInfo_Value(take,'D_STARTOFFS',c.source_start)
        reaper.SetMediaItemTakeInfo_Value(take,'D_PLAYRATE',1/(c.stretch_ratio or 1))
        reaper.SetMediaItemTakeInfo_Value(take,'D_PITCH',c.pitch_semitones or 0)
        reaper.SetMediaItemTakeInfo_Value(take,'B_PPITCH',1)
        if c.fade_in_seconds~=nil or c.fade_out_seconds~=nil then
          reaper.SetMediaItemInfo_Value(item,'D_FADEINLEN',c.fade_in_seconds or 0)
          reaper.SetMediaItemInfo_Value(item,'D_FADEOUTLEN',c.fade_out_seconds or 0)
          reaper.SetMediaItemInfo_Value(item,'D_FADEINLEN_AUTO',0)
          reaper.SetMediaItemInfo_Value(item,'D_FADEOUTLEN_AUTO',0)
          reaper.SetMediaItemInfo_Value(item,'C_FADEINSHAPE',0)
          reaper.SetMediaItemInfo_Value(item,'C_FADEOUTSHAPE',0)
          reaper.SetMediaItemInfo_Value(item,'D_FADEINDIR',0)
          reaper.SetMediaItemInfo_Value(item,'D_FADEOUTDIR',0)
        end
      end
      setext(item,'rostrum_id',c.id,false)
      ::next_clip::
    end
  end
  for ti,t in ipairs(p.tracks) do
    local tr=reaper.GetTrack(0,ti-1)
    for si,send in ipairs(t.sends or {}) do
      local dest
      for di,d in ipairs(p.tracks) do if d.id==send.destination_id then dest=reaper.GetTrack(0,di-1) end end
      local index=si-1
      if index>=reaper.GetTrackNumSends(tr,0) then assert(reaper.CreateTrackSend(tr,dest)==index,'send creation failed') end
      reaper.SetTrackSendInfo_Value(tr,0,index,'D_VOL',10^(send.gain_db/20))
      reaper.SetTrackSendInfo_Value(tr,0,index,'I_MIDIFLAGS',31) -- audio-only send
    end
  end
  reaper.UpdateArrange()
  reaper.Main_SaveProjectEx(0,project_path,8)
  return {saved=true}
end

handlers.readback=function()
  local ok,template=reaper.GetProjExtState(0,'rostrum','template'); assert(ok~=0,'not a Rostrum project')
  local p=json.decode(template)
  p.tempo=rounded(reaper.Master_GetTempo())
  local num,den=reaper.TimeMap_GetTimeSigAtTime(0,0); p.meter=tostring(num)..'/'..tostring(den)
  local tracks=json.array()
  for ti=0,reaper.CountTracks(0)-1 do
    local tr=reaper.GetTrack(0,ti); local id=getext(tr,'rostrum_id',true); local original
    for _,t in ipairs(p.tracks) do if t.id==id then original=t end end
    assert(original,'unmapped native track'); local t=copy(original)
    local _,name=reaper.GetSetMediaTrackInfo_String(tr,'P_NAME','',false)
    if t.name~=nil or name~=t.id then t.name=name end
    local mute=reaper.GetMediaTrackInfo_Value(tr,'B_MUTE')~=0
    if t.muted~=nil or mute then t.muted=mute end
    local vol=reaper.GetMediaTrackInfo_Value(tr,'D_VOL'); assert(vol>0,'zero-volume track cannot map to finite dB')
    local gain=rounded(20*math.log(vol,10)); if t.gain_db~=nil or gain~=0 then t.gain_db=gain end
    local pan=rounded(reaper.GetMediaTrackInfo_Value(tr,'D_PAN')); if t.pan~=nil or pan~=0 then t.pan=pan end
    local fxstart=t.kind=='midi' and 1 or 0
    assert(reaper.TrackFX_GetCount(tr)==fxstart+#(t.effects or {}),'unexpected native effect count')
    for fi,effect in ipairs(t.effects or {}) do
      effect.gain_db=rounded(reaper.TrackFX_GetParam(tr,fxstart+fi-1,0))
    end
    assert(reaper.GetTrackNumSends(tr,0)==#(t.sends or {}),'unexpected native send count')
    for si,send in ipairs(t.sends or {}) do
      local dest=reaper.GetTrackSendInfo_Value(tr,0,si-1,'P_DESTTRACK')
      send.destination_id=getext(dest,'rostrum_id',true)
      send.gain_db=rounded(20*math.log(reaper.GetTrackSendInfo_Value(tr,0,si-1,'D_VOL'),10))
    end
    local clips=json.array()
    for ci=0,reaper.CountTrackMediaItems(tr)-1 do
      local item=reaper.GetTrackMediaItem(tr,ci); local cid=getext(item,'rostrum_id',false); local orig
      for _,c in ipairs(t.clips or {}) do if c.id==cid then orig=c end end
      assert(orig,'unmapped native item'); local c=copy(orig); local take=assert(reaper.GetActiveTake(item))
      if c.kind=='midi' then
        assert(reaper.TakeIsMIDI(take),'expected MIDI take')
        c.start=qn(reaper.GetMediaItemInfo_Value(item,'D_POSITION'))
        c.length=rounded(qn(reaper.GetMediaItemInfo_Value(item,'D_POSITION')+reaper.GetMediaItemInfo_Value(item,'D_LENGTH'))-c.start)
        local _,count,_,texts=reaper.MIDI_CountEvts(take); assert(count==#c.notes,'note identity count mismatch')
        local ids={}
        for ei=0,texts-1 do
          local found,_,_,pos,typ,msg=reaper.MIDI_GetTextSysexEvt(take,ei)
          if found and typ==1 and msg:sub(1,8)=='rostrum:' then
            local identity=json.decode(msg:sub(9)); identity.position=pos; ids[#ids+1]=identity
          end
        end
        assert(#ids==count,'missing native note identities')
        local used={}; local notes=json.array()
        for ni=0,count-1 do
          local found,_,muted,start,finish,channel,pitch,velocity=reaper.MIDI_GetNote(take,ni)
          assert(found and not muted,'unsupported muted/missing note')
          local identity
          for ii,v in ipairs(ids) do if not used[ii] and math.abs(v.position-start)<0.01 and v.pitch==pitch and v.channel==channel then identity=v; used[ii]=true; break end end
          assert(identity,'native note identity onset mismatch')
          local n=copy(c.notes[identity.index]); assert(n.id==identity.id,'note ID mismatch')
          n.pitch=pitch; n.velocity=velocity
          n.start=rounded(reaper.MIDI_GetProjQNFromPPQPos(take,start)-c.start)
          n.duration=rounded(reaper.MIDI_GetProjQNFromPPQPos(take,finish)-reaper.MIDI_GetProjQNFromPPQPos(take,start))
          if n.channel~=nil or channel~=0 then n.channel=channel end
          notes[identity.index]=n
        end
        c.notes=notes
      else
        c.timeline_start_beats=qn(reaper.GetMediaItemInfo_Value(item,'D_POSITION'))
        c.source_start=rounded(reaper.GetMediaItemTakeInfo_Value(take,'D_STARTOFFS'))
        local rate=reaper.GetMediaItemTakeInfo_Value(take,'D_PLAYRATE')
        c.stretch_ratio=rounded(1/rate)
        c.source_end=rounded(c.source_start+reaper.GetMediaItemInfo_Value(item,'D_LENGTH')*rate)
        c.pitch_semitones=rounded(reaper.GetMediaItemTakeInfo_Value(take,'D_PITCH'))
        if c.fade_in_seconds~=nil then c.fade_in_seconds=rounded(reaper.GetMediaItemInfo_Value(item,'D_FADEINLEN')) end
        if c.fade_out_seconds~=nil then c.fade_out_seconds=rounded(reaper.GetMediaItemInfo_Value(item,'D_FADEOUTLEN')) end
      end
      clips[#clips+1]=c
    end
    if t.clips~=nil or #clips>0 then t.clips=clips end
    tracks[#tracks+1]=t
  end
  p.tracks=tracks; return p
end
handlers.save=function() reaper.Main_SaveProjectEx(0,project_path,8); return {saved=true} end
-- Only this isolated worker's saved project is opened. A plain path can trigger
-- a modal save prompt even after Main_SaveProjectEx when the project was untitled.
handlers.reopen=function() reaper.Main_openProject('noprompt:'..project_path); return handlers.readback() end
handlers.native_ids=function()
  local result={}
  for ti=0,reaper.CountTracks(0)-1 do
    local tr=reaper.GetTrack(0,ti)
    local track_id=getext(tr,'rostrum_id',true)
    result[track_id]={guid=reaper.GetTrackGUID(tr),items={}}
    for ci=0,reaper.CountTrackMediaItems(tr)-1 do
      local item=reaper.GetTrackMediaItem(tr,ci)
      local _,guid=reaper.GetSetMediaItemInfo_String(item,'GUID','',false)
      result[track_id].items[getext(item,'rostrum_id',false)]=guid
    end
  end
  return result
end
handlers.render=function(a)
  assert(a.channels==1 or a.channels==2,'unsupported render channels')
  local finish=a['end']; if finish==nil or finish==json.null then finish=reaper.GetProjectLength(0)+0.1 end
  local start=a.start; if start==nil or start==json.null then start=0 end
  reaper.GetSetProjectInfo(0,'RENDER_SETTINGS',0,true)
  reaper.GetSetProjectInfo(0,'RENDER_BOUNDSFLAG',0,true)
  reaper.GetSetProjectInfo(0,'RENDER_STARTPOS',start,true)
  reaper.GetSetProjectInfo(0,'RENDER_ENDPOS',finish,true)
  reaper.GetSetProjectInfo(0,'RENDER_TAILFLAG',0,true)
  reaper.GetSetProjectInfo(0,'RENDER_SRATE',a.sample_rate,true)
  reaper.GetSetProjectInfo(0,'RENDER_CHANNELS',a.channels,true)
  reaper.GetSetProjectInfo_String(0,'RENDER_FILE',workspace..'/renders',true)
  reaper.GetSetProjectInfo_String(0,'RENDER_PATTERN',a.render_id,true)
  reaper.GetSetProjectInfo_String(0,'RENDER_FORMAT','ZXZhdxgAAA==',true)
  reaper.Main_SaveProjectEx(0,project_path,8)
  reaper.Main_OnCommand(42230,0)
  return {path=workspace..'/renders/'..a.render_id..'.wav'}
end
local function process(request)
  assert(request.protocol==1,'unsupported protocol')
  assert(type(request.id)=='string','missing request ID')
  local handler=assert(handlers[request.command],'unsupported command: '..tostring(request.command))
  return handler(request.arguments or {})
end
local function poll()
  local names={}; local i=0
  while true do local name=reaper.EnumerateFiles(workspace..'/requests',i); if not name then break end
    if name:match('^%d+%.json$') then names[#names+1]=name end; i=i+1 end
  table.sort(names)
  for _,name in ipairs(names) do
    local response=workspace..'/responses/'..name
    local exists=io.open(response,'rb')
    if exists then exists:close() else
      local id=name:match('^(%d+)')
      local ok,result=pcall(function() local r=load(workspace..'/requests/'..name); assert(r.id==id,'filename/ID mismatch'); return process(r) end)
      write(response,{protocol=1,id=id,ok=ok,result=ok and result or json.null,
        error=ok and json.null or {kind='reaper_error',message=tostring(result)}})
    end
  end
  reaper.defer(poll)
end
RostrumBridge={dispatch=process,capabilities=handlers.capabilities}
poll()
