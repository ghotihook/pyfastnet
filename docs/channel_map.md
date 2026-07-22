# B&G channel → name → Signal K path (master reference)

**Generated** from `fastnet_decoder.channel_map()` (pyfastnet 3.0.0). Do not hand-edit — regenerate with `python docs/generate_channel_map.py`.

This is the authoritative map, derived from the projection tables so it stays in step with what `project()` actually emits. `kind`: *standard* = SK path, *vendor* = `bandg.*`, *routed(M/T)* = Magnetic|True chosen from layout, *collapsed* = redundant variant folded onto a sibling, *drop* = not emitted.

> Position (`navigation.position`) and backlight come from command frames (LatLon / Light Intensity), not channel ids, so they are not in this table.

| ID | B&G name | Signal K path | Unit | Kind |
|----|----------|---------------|------|------|
| 0x00 | Node Reset | `—` |  | drop |
| 0x0B | Rudder Angle | `steering.rudderAngle` | rad | standard |
| 0x0C | Linear 5 | `—` |  | unmapped |
| 0x0D | Linear 6 | `—` |  | unmapped |
| 0x0E | Linear 7 | `—` |  | unmapped |
| 0x0F | Linear 8 | `—` |  | unmapped |
| 0x10 | Linear 9 | `—` |  | unmapped |
| 0x11 | Linear 10 | `—` |  | unmapped |
| 0x12 | Linear 11 | `—` |  | unmapped |
| 0x13 | Linear 12 | `—` |  | unmapped |
| 0x14 | Linear 13 | `—` |  | unmapped |
| 0x15 | Linear 14 | `—` |  | unmapped |
| 0x16 | Linear 15 | `—` |  | unmapped |
| 0x17 | Linear 16 | `—` |  | unmapped |
| 0x1C | Air Temperature (°F) | `→ environment.outside.temperature` |  | collapsed |
| 0x1D | Air Temperature (°C) | `environment.outside.temperature` | K | standard |
| 0x1E | Sea Temperature (°F) | `→ environment.water.temperature` |  | collapsed |
| 0x1F | Sea Temperature (°C) | `environment.water.temperature` | K | standard |
| 0x27 | Head/Lift Trend | `bandg.performance.headLiftTrend` |  | vendor |
| 0x29 | Off Course | `bandg.steering.offCourse` | rad | vendor |
| 0x32 | Tacking Performance | `bandg.performance.tacking` | ratio | vendor |
| 0x33 | Reaching Performance | `bandg.performance.reaching` | ratio | vendor |
| 0x34 | Heel Angle | `navigation.attitude.roll` | rad | standard |
| 0x35 | Optimum Wind Angle | `bandg.performance.optimumWindAngle` | rad | vendor |
| 0x36 | Depth Sounder Receiver Gain | `—` |  | drop |
| 0x37 | Depth Sounder Noise | `—` |  | drop |
| 0x38 | Linear 1 | `—` |  | unmapped |
| 0x39 | Linear 2 | `—` |  | unmapped |
| 0x3A | Linear 3 | `—` |  | unmapped |
| 0x3B | Linear 4 | `—` |  | unmapped |
| 0x3C | Rate Motion | `bandg.motion.rate` | ? | vendor |
| 0x41 | Boatspeed (Knots) | `navigation.speedThroughWater` | m/s | standard |
| 0x42 | Boatspeed (Raw) | `bandg.navigation.rawSpeedThroughWater` |  | vendor |
| 0x44 | Yaw rate | `navigation.rateOfTurn` | rad | standard |
| 0x46 | Autopilot Speed Fixed (Knots) | `bandg.steering.autopilot.fixedSpeed` | m/s | vendor |
| 0x49 | Heading | `navigation.heading{Magnetic,True}` | rad | routed(M/T) |
| 0x4A | Heading (Raw) | `bandg.navigation.rawHeading` |  | vendor |
| 0x4D | Apparent Wind Speed (Knots) | `→ environment.wind.speedApparent` |  | collapsed |
| 0x4E | Apparent Wind Speed (Raw) | `bandg.wind.rawSpeedApparent` |  | vendor |
| 0x4F | Apparent Wind Speed (m/s) | `environment.wind.speedApparent` | m/s | standard |
| 0x50 | from NMEA | `—` |  | drop |
| 0x51 | Apparent Wind Angle | `environment.wind.angleApparent` | rad | standard |
| 0x52 | Apparent Wind Angle (Raw) | `bandg.wind.rawAngleApparent` |  | vendor |
| 0x53 | Target TWA | `performance.targetAngle` | rad | standard |
| 0x55 | True Wind Speed (Knots) | `→ environment.wind.speedTrue` |  | collapsed |
| 0x56 | True Wind Speed (m/s) | `environment.wind.speedTrue` | m/s | standard |
| 0x57 | Measured Wind Speed (Knots) | `bandg.wind.measuredSpeed` | m/s | vendor |
| 0x59 | True Wind Angle | `environment.wind.angleTrueWater` | rad | standard |
| 0x5A | Measured Wind Angle Deg | `bandg.wind.measuredAngle` | rad | vendor |
| 0x64 | Average Speed (Knots) | `bandg.navigation.speedThroughWaterAverage` | m/s | vendor |
| 0x65 | Average Speed (raw) | `→ bandg.navigation.speedThroughWaterAverage` |  | collapsed |
| 0x68 | Request for Data | `—` |  | drop |
| 0x69 | Course (HDG + Leeway) | `bandg.navigation.courseThroughWater` | rad | vendor |
| 0x6A | Act for Data | `—` |  | drop |
| 0x6D | True Wind Direction | `environment.wind.direction{Magnetic,True}` | rad | routed(M/T) |
| 0x6F | Next Leg Apparent Wind Angle | `bandg.performance.nextLeg.angleApparent` | rad | vendor |
| 0x70 | Next Leg Target Boat Speed | `bandg.performance.nextLeg.targetSpeed` | m/s | vendor |
| 0x71 | Next Leg Apparent Wind Speed | `bandg.performance.nextLeg.speedApparent` | m/s | vendor |
| 0x75 | Timer | `bandg.time.timer` | s | vendor |
| 0x7C | Polar Performance | `performance.polarSpeedRatio` | ratio | standard |
| 0x7D | Target Boatspeed | `performance.targetSpeed` | m/s | standard |
| 0x7F | Velocity Made Good (Knots) | `performance.velocityMadeGood` | m/s | standard |
| 0x81 | Dead Reckoning Distance | `bandg.navigation.deadReckoning.distance` | m | vendor |
| 0x82 | Leeway | `navigation.leewayAngle` | rad | standard |
| 0x83 | Tidal Drift | `environment.current.drift` | m/s | standard |
| 0x84 | Tidal Set | `environment.current.set{Magnetic,True}` | rad | routed(M/T) |
| 0x85 | Upwash | `bandg.wind.upwash` | rad | vendor |
| 0x86 | Barometric Pressure Trend | `bandg.environment.pressureTrend` | Pa | vendor |
| 0x87 | Barometric Pressure | `environment.outside.pressure` | Pa | standard |
| 0x8D | Battery Volts | `electrical.batteries.{id}.voltage` | V | standard |
| 0x9A | Heading on Next Tack | `performance.tackMagnetic` | rad | standard |
| 0x9B | Fore/Aft Trim | `navigation.attitude.pitch` | rad | standard |
| 0x9C | Mast Angle | `bandg.mast.rotation` | rad | vendor |
| 0x9D | Wind Angle to the Mast | `bandg.mast.windAngle` | rad | vendor |
| 0x9E | Pitch Rate (Motion) | `bandg.motion.pitchRate` | rad | vendor |
| 0xA6 | Autopilot Compass Target | `steering.autopilot.target.headingMagnetic` | rad | standard |
| 0xAF | Autopilot Off Course | `bandg.steering.autopilot.offCourse` | rad | vendor |
| 0xB5 | Autopilot Mode | `steering.autopilot.state` | enum | standard |
| 0xC1 | Depth (Meters) | `environment.depth.belowTransducer` | m | standard(depth fallback) |
| 0xC2 | Depth (Feet) | `environment.depth.belowTransducer` | m | standard(depth fallback) |
| 0xC3 | Depth (Fathoms) | `environment.depth.belowTransducer` | m | standard(depth fallback) |
| 0xCD | Stored Log (NM) | `navigation.log` | m | standard |
| 0xCF | Trip Log (NM) | `navigation.trip.log` | m | standard |
| 0xD3 | Dead Reckoning Course | `bandg.navigation.deadReckoning.course` | rad | vendor |
| 0xDC | Local Time | `bandg.time.local` | s | vendor |
| 0xDD | UTC Time | `—` |  | unmapped |
| 0xE0 | Bearing Wpt. to Wpt. (True) | `navigation.courseGreatCircle.bearingTrackTrue` | rad | standard |
| 0xE1 | Bearing Wpt. to Wpt. (Mag) | `navigation.courseGreatCircle.bearingTrackMagnetic` | rad | standard |
| 0xE2 | Layline Distance | `navigation.racing.layline.distance` | m | standard |
| 0xE3 | Bearing to Waypoint (Rhumb True) | `navigation.courseRhumbline.nextPoint.bearingTrue` | rad | standard |
| 0xE4 | Bearing to Waypoint (Rhumb Mag) | `navigation.courseRhumbline.nextPoint.bearingMagnetic` | rad | standard |
| 0xE5 | Bearing to Waypoint (G.C. True) | `navigation.courseGreatCircle.nextPoint.bearingTrue` | rad | standard |
| 0xE6 | Bearing to Waypoint (G.C. Mag) | `navigation.courseGreatCircle.nextPoint.bearingMagnetic` | rad | standard |
| 0xE7 | Distance to Waypoint (Rhumb) | `navigation.courseRhumbline.nextPoint.distance` | m | standard |
| 0xE8 | Distance to Waypoint (G.C.) | `navigation.courseGreatCircle.nextPoint.distance` | m | standard |
| 0xE9 | Course Over Ground (True) | `navigation.courseOverGroundTrue` | rad | standard |
| 0xEA | Course Over Ground (Mag) | `navigation.courseOverGroundMagnetic` | rad | standard |
| 0xEB | Speed Over Ground | `navigation.speedOverGround` | m/s | standard |
| 0xEC | VMG to Waypoint (VMC) | `navigation.courseGreatCircle.nextPoint.velocityMadeGood` | m/s | standard |
| 0xED | Time to Waypoint | `navigation.courseGreatCircle.nextPoint.timeToGo` | s | standard |
| 0xEE | Cross Track Error | `navigation.courseGreatCircle.crossTrackError` | m | standard |
| 0xEF | Remote 0 | `—` |  | unmapped |
| 0xF0 | Remote 1 | `—` |  | unmapped |
| 0xF1 | Remote 2 | `—` |  | unmapped |
| 0xF2 | Remote 3 | `—` |  | unmapped |
| 0xF3 | Remote 4 | `—` |  | unmapped |
| 0xF4 | Remote 5 | `—` |  | unmapped |
| 0xF5 | Remote 6 | `—` |  | unmapped |
| 0xF6 | Remote 7 | `—` |  | unmapped |
| 0xF7 | Remote 8 | `—` |  | unmapped |
| 0xF8 | Remote 9 | `—` |  | unmapped |
| 0xF9 | Course to Sail | `bandg.performance.courseToSail` | rad | vendor |
| 0xFA | Next Waypoint Distance | `navigation.courseGreatCircle.nextPoint.distance` | m | standard |
| 0xFB | Time to Layline | `navigation.racing.layline.time` | s | standard |
