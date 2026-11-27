package com.seibel.distanthorizons.neoforge.mixins.server;

import com.seibel.distanthorizons.common.wrappers.worldGeneration.mimicObject.WorldGenStructFeatManager;
import net.minecraft.server.level.ServerLevel;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

#if MC_VER < MC_1_19_2
import net.minecraft.world.level.StructureFeatureManager;
#else
import net.minecraft.world.level.StructureManager;
#endif

/**
 * Some mods bypass the structure manager passed into world gen and instead call
 * {@code worldGenLevel.getLevel().structureManager()} directly. <br>
 * When that happens on a DH world gen thread it will trigger a call on MC's server thread
 * will cause tick lag. <br><br>
 *
 * This redirects those calls to DH's structure manager for the region being generated. <br><br>
 *
 * Example: Villages and Pillages' TreeFeature mixin.
 *
 * @see WorldGenStructFeatManager#getThreadOverride(ServerLevel)
 */
@Mixin(ServerLevel.class)
public class MixinServerLevelStructureManager
{
	#if MC_VER < MC_1_19_2
	@Inject(method = "structureFeatureManager", at = @At("HEAD"), cancellable = true)
	private void overrideStructureManager(CallbackInfoReturnable<StructureFeatureManager> cir)
	#else
	@Inject(method = "structureManager", at = @At("HEAD"), cancellable = true)
	private void overrideStructureManager(CallbackInfoReturnable<StructureManager> cir)
	#endif
	{
		WorldGenStructFeatManager override = WorldGenStructFeatManager.getThreadOverride((ServerLevel) (Object) this);
		if (override != null)
		{
			cir.setReturnValue(override);
		}
	}
	
	
	
}
