#if UNITY_EDITOR
using UnityEngine;
using UnityEditor;

/// <summary>
/// メニュー koten2026 > Create Hand Points から実行する。
/// OscManager に HandReceiver がアタッチされている前提。
/// </summary>
public static class HandPointsGenerator
{
    [MenuItem("koten2026/Create Hand Points")]
    static void CreateHandPoints()
    {
        var receiver = Object.FindFirstObjectByType<HandReceiver>();
        if (receiver == null)
        {
            Debug.LogError("[HandPointsGenerator] HandReceiver がシーンに見つかりません。OscManager にアタッチしてから実行してください。");
            return;
        }

        // マテリアル（Transparent）を作成
        var mat = new Material(Shader.Find("Universal Render Pipeline/Lit"));
        if (mat.HasProperty("_Surface"))
        {
            mat.SetFloat("_Surface", 1f); // 0=Opaque, 1=Transparent
            mat.SetFloat("_Blend", 0f);
            mat.enableInstancing = true;
            mat.renderQueue = 3000;
        }
        // Built-in の場合のフォールバック
        if (mat.shader.name == "Hidden/InternalErrorShader")
        {
            mat = new Material(Shader.Find("Standard"));
            mat.SetFloat("_Mode", 3f); // Transparent
        }
        AssetDatabase.CreateAsset(mat, "Assets/HandPointMaterial.mat");

        receiver.leftPoints  = CreatePoints("LeftHand",  21, mat, receiver.transform.parent ?? receiver.transform.root);
        receiver.rightPoints = CreatePoints("RightHand", 21, mat, receiver.transform.parent ?? receiver.transform.root);

        // Renderer 配列も自動登録
        var leftRenderers  = new Renderer[21];
        var rightRenderers = new Renderer[21];
        for (int i = 0; i < 21; i++)
        {
            leftRenderers[i]  = receiver.leftPoints[i].GetComponent<Renderer>();
            rightRenderers[i] = receiver.rightPoints[i].GetComponent<Renderer>();
        }
        receiver.leftRenderers  = leftRenderers;
        receiver.rightRenderers = rightRenderers;

        EditorUtility.SetDirty(receiver);
        Debug.Log("[HandPointsGenerator] LeftHand / RightHand を生成しました。");
    }

    static Transform[] CreatePoints(string parentName, int count, Material mat, Transform sceneRoot)
    {
        // 既存の同名オブジェクトを削除してから作り直す
        var existing = GameObject.Find(parentName);
        if (existing != null) Object.DestroyImmediate(existing);

        var parent = new GameObject(parentName);
        Undo.RegisterCreatedObjectUndo(parent, "Create " + parentName);

        var points = new Transform[count];
        for (int i = 0; i < count; i++)
        {
            var sphere = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            sphere.name = $"point_{i:D2}";
            sphere.transform.SetParent(parent.transform, false);
            sphere.transform.localScale = Vector3.one * 0.1f;
            sphere.GetComponent<Renderer>().sharedMaterial = mat;
            // コライダーは不要
            Object.DestroyImmediate(sphere.GetComponent<Collider>());
            points[i] = sphere.transform;
        }
        return points;
    }
}
#endif
