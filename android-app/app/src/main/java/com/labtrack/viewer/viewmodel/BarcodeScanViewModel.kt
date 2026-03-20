package com.labtrack.viewer.viewmodel

import androidx.lifecycle.ViewModel
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import javax.inject.Inject

@HiltViewModel
class BarcodeScanViewModel @Inject constructor() : ViewModel() {

    private val _detectedBarcode = MutableStateFlow<String?>(null)
    val detectedBarcode: StateFlow<String?> = _detectedBarcode.asStateFlow()

    private val _hasCameraPermission = MutableStateFlow(false)
    val hasCameraPermission: StateFlow<Boolean> = _hasCameraPermission.asStateFlow()

    fun onBarcodeDetected(specimenId: String) {
        _detectedBarcode.value = specimenId
    }

    fun setCameraPermission(granted: Boolean) {
        _hasCameraPermission.value = granted
    }

    fun resetBarcode() {
        _detectedBarcode.value = null
    }
}
