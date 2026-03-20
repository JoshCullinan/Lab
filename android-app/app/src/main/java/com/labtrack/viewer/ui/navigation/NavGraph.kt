package com.labtrack.viewer.ui.navigation

import androidx.compose.runtime.Composable
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.labtrack.viewer.ui.screens.BarcodeScanScreen
import com.labtrack.viewer.ui.screens.EpisodeListScreen
import com.labtrack.viewer.ui.screens.HomeScreen
import com.labtrack.viewer.ui.screens.LoginScreen
import com.labtrack.viewer.ui.screens.PatientListScreen
import com.labtrack.viewer.ui.screens.ResultsScreen
import com.labtrack.viewer.viewmodel.AuthViewModel
import com.labtrack.viewer.viewmodel.SearchViewModel

@Composable
fun NavGraph() {
    val navController = rememberNavController()
    val authViewModel: AuthViewModel = hiltViewModel()
    val searchViewModel: SearchViewModel = hiltViewModel()

    val startDest = if (authViewModel.hasCredentials()) Routes.HOME else Routes.LOGIN

    NavHost(navController = navController, startDestination = startDest) {

        composable(Routes.LOGIN) {
            LoginScreen(
                viewModel = authViewModel,
                onLoginSuccess = {
                    navController.navigate(Routes.HOME) {
                        popUpTo(Routes.LOGIN) { inclusive = true }
                    }
                }
            )
        }

        composable(Routes.HOME) {
            HomeScreen(
                searchViewModel = searchViewModel,
                onScanClick = { navController.navigate(Routes.BARCODE_SCAN) },
                onPatientListReady = { navController.navigate(Routes.PATIENT_LIST) },
                onResultsReady = { navController.navigate(Routes.RESULTS) },
                onEpisodeListReady = { navController.navigate(Routes.EPISODE_LIST) },
                onClearSession = {
                    authViewModel.clearSession()
                    navController.navigate(Routes.LOGIN) {
                        popUpTo(Routes.HOME) { inclusive = true }
                    }
                }
            )
        }

        composable(Routes.BARCODE_SCAN) {
            BarcodeScanScreen(
                searchViewModel = searchViewModel,
                onBarcodeDetected = { specimenId ->
                    searchViewModel.searchBySpecimen(specimenId)
                    navController.navigate(Routes.RESULTS) {
                        popUpTo(Routes.HOME)
                    }
                },
                onBack = { navController.popBackStack() }
            )
        }

        composable(Routes.PATIENT_LIST) {
            PatientListScreen(
                searchViewModel = searchViewModel,
                onPatientSelected = { hit ->
                    searchViewModel.openPatient(hit)
                    navController.navigate(Routes.RESULTS)
                },
                onPatientFolderSelected = { hit ->
                    searchViewModel.listEpisodes(hit)
                    navController.navigate(Routes.EPISODE_LIST)
                },
                onBack = { navController.popBackStack() }
            )
        }

        composable(Routes.EPISODE_LIST) {
            EpisodeListScreen(
                searchViewModel = searchViewModel,
                onEpisodeSelected = { rowIndex ->
                    searchViewModel.loadEpisodeResults(rowIndex)
                    navController.navigate(Routes.RESULTS)
                },
                onLoadAll = {
                    searchViewModel.loadAllEpisodeResults()
                    navController.navigate(Routes.RESULTS)
                },
                onBack = { navController.popBackStack() }
            )
        }

        composable(Routes.RESULTS) {
            ResultsScreen(
                searchViewModel = searchViewModel,
                onBack = { navController.popBackStack() }
            )
        }
    }
}
