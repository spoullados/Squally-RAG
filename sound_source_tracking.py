import asyncio
import math
import navel

async def main():
    print("Listening forever, press Ctrl+C to stop...")
    async with navel.Robot() as robot:
        while True:
            perc = await robot.next_frame()
            for channel, metadata in enumerate(perc.sst_tracks_latest):

                if metadata.activity > 0.5:
                    print(
                        f"Heard a sound on channel {channel + 1} at {metadata.loc}"
                    )
                    angle = math.atan2(metadata.loc.y, metadata.loc.x)  # Angle in radians
                    angle_degrees = math.degrees(angle)  # Convert to degrees if needed

                    print(f"Angle in radians: {angle}")
                    print(f"Angle in degrees: {angle_degrees}")

if __name__ == "__main__":
    asyncio.run(main())

